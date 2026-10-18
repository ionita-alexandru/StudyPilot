"""Régressions de stockage : collisions et verrous Windows simulés.

Les vraies opérations concurrentes tournent aussi sous Linux. Les winerror
sont injectés : ces tests ne prétendent pas reproduire le PC utilisateur.
"""
import errno
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch

from src.storage import repository


def windows_error(code=32):
    error = PermissionError(errno.EACCES, 'Fichier utilisé par un autre processus')
    error.winerror = code
    return error


class AtomicStorageTests(unittest.TestCase):
    def test_unicode_round_trip_and_no_temporary_left(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'cours'/'pedagogy.json'
            repository.write_json_atomic(path, {'preuve':'ω ∈ E, cₙ = (aₙ − ibₙ)/2'})
            self.assertEqual(repository.read_json(path)['preuve'],'ω ∈ E, cₙ = (aₙ − ibₙ)/2')
            self.assertEqual(list(path.parent.glob('*.tmp')),[])

    def test_two_overlapping_writes_do_not_share_temporary(self):
        self._overlapping_writes(inject_lock=False)

    def test_overlapping_writes_retry_windows_lock_without_second_barrier(self):
        self._overlapping_writes(inject_lock=True)

    def _overlapping_writes(self, *, inject_lock):
        with TemporaryDirectory() as root:
            path=Path(root)/'pedagogy.json'
            barrier=threading.Barrier(2); failures=[]; temporaries=set()
            guard=threading.Lock(); injected=False; attempts=[]
            replace=repository.os.replace
            def overlapping(source,destination):
                nonlocal injected
                # Synchroniser seulement la PREMIÈRE tentative de chaque
                # écriture. Un retry Windows ne doit pas attendre un écrivain
                # qui a déjà réussi et quitté la barrière.
                with guard:
                    first = source not in temporaries
                    temporaries.add(source)
                    attempts.append(source)
                if first:
                    barrier.wait(timeout=5)
                with guard:
                    should_fail = inject_lock and not injected
                    if should_fail:
                        injected = True
                if should_fail:
                    raise windows_error(32)
                replace(source,destination)
            def worker(index):
                try:
                    repository.write_json_atomic(path,{'worker':index,'payload':[index]*500})
                except BaseException as error:
                    failures.append(error)
            with patch.object(repository.os,'replace',side_effect=overlapping):
                threads=[threading.Thread(target=worker,args=(i,)) for i in range(2)]
                for t in threads:t.start()
                for t in threads:t.join(timeout=10)
            self.assertFalse(any(t.is_alive() for t in threads))
            self.assertFalse(failures,failures)
            self.assertEqual(len(temporaries),2)
            if inject_lock:
                self.assertTrue(injected)
                self.assertGreaterEqual(len(attempts),3)
            saved=repository.read_json(path)
            self.assertEqual(saved['payload'],[saved['worker']]*500)
            self.assertEqual(list(path.parent.glob('*.tmp')),[])

    def test_windows_transient_lock_retries_then_commits(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'pedagogy.json'; repository.write_json_atomic(path,{'old':True})
            replace=repository.os.replace; calls=[]
            def locked_once(source,destination):
                calls.append(source)
                if len(calls)==1:raise windows_error()
                replace(source,destination)
            with patch.object(repository.os,'replace',side_effect=locked_once), patch.object(repository.time,'sleep') as sleep:
                repository.write_json_atomic(path,{'new':True})
            self.assertEqual(repository.read_json(path),{'new':True})
            self.assertEqual(len(calls),2); sleep.assert_called_once_with(0.05)

    def test_persistent_lock_is_bounded_preserves_old_json_and_explains_error(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'pedagogy.json';repository.write_json_atomic(path,{'old':True})
            old=path.read_bytes()
            with patch.object(repository.os,'replace',side_effect=windows_error(33)) as replace,patch.object(repository.time,'sleep') as sleep:
                with self.assertRaises(repository.StorageError) as caught:
                    repository.write_json_atomic(path,{'new':True})
            self.assertEqual(replace.call_count,6);self.assertEqual(sleep.call_count,5)
            self.assertEqual(path.read_bytes(),old)
            self.assertIn('winerror=33',str(caught.exception))
            self.assertIn('remplacement atomique',str(caught.exception))
            self.assertEqual(list(path.parent.glob('*.tmp')),[])

    def test_nontransient_error_is_not_retried(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'pedagogy.json';repository.write_json_atomic(path,{'old':True})
            with patch.object(repository.os,'replace',side_effect=OSError(errno.ENOSPC,'Plus de place')),patch.object(repository.time,'sleep') as sleep:
                with self.assertRaises(repository.StorageError) as caught:repository.write_json_atomic(path,{'new':True})
            sleep.assert_not_called()
            self.assertIn('errno=28',str(caught.exception))
            self.assertEqual(repository.read_json(path),{'old':True})

    def test_cleanup_failure_does_not_mask_original_failure(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'pedagogy.json'
            with patch.object(repository.os,'replace',side_effect=windows_error()),patch.object(repository.time,'sleep'),patch.object(Path,'unlink',side_effect=PermissionError('Nettoyage refusé')):
                with self.assertRaises(repository.StorageError) as caught:repository.write_json_atomic(path,{'new':True})
            self.assertIn('winerror=32',str(caught.exception))
            self.assertIn('temporaire non supprimé',str(caught.exception))

    def test_directory_failure_and_serialization_failure_are_actionable(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'pedagogy.json'
            with patch.object(Path,'mkdir',side_effect=PermissionError('Dossier interdit')):
                with self.assertRaises(repository.StorageError) as caught:repository.write_json_atomic(path,{})
            self.assertIn('création du dossier',str(caught.exception))
            with self.assertRaises(repository.StorageError) as caught:repository.write_json_atomic(path,{'bad':object()})
            self.assertIn('sérialisation',str(caught.exception))
            self.assertFalse(path.exists())

    def test_read_error_keeps_underlying_details(self):
        with TemporaryDirectory() as root:
            path=Path(root)/'pedagogy.json';path.write_text('{broken')
            with self.assertRaises(repository.StorageError) as caught:repository.read_json(path)
            self.assertIn('JSONDecodeError',str(caught.exception))
