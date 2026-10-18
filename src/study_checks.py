"""Vérifications locales bornées. Aucun eval, exec, import ou accès système."""
import ast
from fractions import Fraction
import json
import re


def number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 80:
        raise ValueError('Nombre non pris en charge.')
    if not re.fullmatch(r'-?\d{1,18}(?:/\d{1,18}|\.\d{1,18})?', str(value)):
        raise ValueError('Utiliser un nombre décimal ou une fraction de taille limitée.')
    result = Fraction(str(value))
    if result.numerator.bit_length() > 256 or result.denominator.bit_length() > 256:
        raise ValueError('Nombre trop grand.')
    return result


def expression(text, bindings=None):
    if not isinstance(text, str) or len(text) > 300:
        raise ValueError('Expression trop longue.')
    tree = ast.parse(text, mode='eval')
    if len(list(ast.walk(tree))) > 70:
        raise ValueError('Expression trop complexe.')
    def visit(node):
        if isinstance(node, ast.Constant):
            return number(node.value)
        if isinstance(node, ast.Name) and node.id in (bindings or {}):
            return bindings[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            result = visit(node.operand)
            return -result if isinstance(node.op, ast.USub) else result
        if not isinstance(node, ast.BinOp):
            raise ValueError('Seule l’arithmétique explicite est prise en charge.')
        left, right = visit(node.left), visit(node.right)
        if isinstance(node.op, ast.Add): result = left + right
        elif isinstance(node.op, ast.Sub): result = left - right
        elif isinstance(node.op, ast.Mult): result = left * right
        elif isinstance(node.op, ast.Div): result = left / right
        elif isinstance(node.op, ast.Pow) and right.denominator == 1 and abs(right) <= 20:
            result = left ** int(right)
        else: raise ValueError('Opération hors du périmètre de vérification.')
        if result.numerator.bit_length() > 512 or result.denominator.bit_length() > 512:
            raise ValueError('Résultat trop grand.')
        return result
    return visit(tree.body)


def calculate(request):
    operation = request.get('operation')
    if operation == 'arithmetic':
        actual = expression(request['expression'])
        return str(actual), actual == number(request['expected']), 'calcul arithmétique'
    if operation == 'matrix_vector':
        matrix, vector = request['matrix'], request['vector']
        if not isinstance(matrix, list) or not isinstance(vector, list) or not 1 <= len(matrix) <= 6 or not 1 <= len(vector) <= 6:
            raise ValueError('Dimensions hors du périmètre de vérification.')
        if any(not isinstance(row, list) or len(row) != len(vector) for row in matrix):
            raise ValueError('Dimensions incompatibles.')
        vector = [number(v) for v in vector]
        actual = [sum((number(x)*y for x,y in zip(row,vector)), Fraction(0)) for row in matrix]
        expected = request['expected']
        if not isinstance(expected, list) or len(expected) != len(actual):
            raise ValueError('Résultat attendu incompatible.')
        return [str(v) for v in actual], actual == [number(v) for v in expected], 'produit matrice-vecteur'
    if operation == 'python_function':
        code = request['code']
        if not isinstance(code, str) or len(code) > 500:
            raise ValueError('Code hors du périmètre de vérification.')
        tree = ast.parse(code)
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            raise ValueError('Une seule fonction arithmétique est prise en charge.')
        func = tree.body[0]
        args = func.args
        if (func.decorator_list or func.returns or args.defaults or args.kw_defaults or args.posonlyargs
                or args.vararg or args.kwarg or args.kwonlyargs or len(args.args) != 1 or args.args[0].annotation
                or len(func.body) != 1 or not isinstance(func.body[0], ast.Return)):
            raise ValueError('Seule une fonction à un paramètre et un return arithmétique est prise en charge.')
        actual = expression(ast.unparse(func.body[0].value), {args.args[0].arg: number(request['argument'])})
        return str(actual), actual == number(request['expected']), 'fonction arithmétique évaluée avec un interpréteur limité'
    raise ValueError('Vérification non prise en charge.')


INSTRUCTIONS = r'''Si ta réponse applique une des opérations numériques prises en charge ci-dessous, joins UN bloc technique final pour le contrôle local
```verification contenant uniquement un objet JSON parmi :
{"operation":"arithmetic","expression":"3*2**3","expected":"24"}
{"operation":"matrix_vector","matrix":[[2,1],[1,2]],"vector":[1,1],"expected":[3,3]}
{"operation":"python_function","code":"def doubler(nombre):\n    return 2 * nombre","argument":"3","expected":"6"}
Ferme le bloc avec ```. Reprends EXACTEMENT les données et le résultat de ton explication, pas ces exemples par défaut.
Le serveur vérifie localement, sans exécuter du code arbitraire. Ce bloc sera remplacé par le constat du calcul.
Pas de bloc pour un simple énoncé d'exercice ou si ces opérations ne conviennent pas. Ne prétends pas qu'un contrôle
valide toute la réponse, les hypothèses ou une démonstration. Le statut de vérification est donné par le serveur.'''


def verify_response(text):
    checks = []
    pattern = re.compile(r'```verification\s*\n([\s\S]*?)```')
    def replace(match):
        if checks:
            return ''
        try:
            request = json.loads(match[1])
            if not isinstance(request, dict): raise ValueError('Objet attendu.')
            actual, passed, kind = calculate(request)
            checks.append(dict(passed=passed, operation=request['operation'], result=actual))
            value = ', '.join(actual) if isinstance(actual, list) else actual
            label = 'Calcul contrôlé' if passed else 'Écart détecté dans le calcul'
            return f'\n\n**{label}** — {kind} : `{value}`. Ce contrôle porte uniquement sur ce calcul.'
        except (ValueError, SyntaxError, KeyError, TypeError, ZeroDivisionError, OverflowError):
            checks.append(dict(passed=False, operation='unsupported'))
            return '\n\nCe calcul n’a pas pu être contrôlé automatiquement.'
    return pattern.sub(replace, text), checks
