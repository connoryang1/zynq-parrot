from pathlib import Path
import tempfile
import unittest
from run import CASES,validate_paths

class Tests(unittest.TestCase):
    def test_required_boundary(self):
        self.assertEqual([i for s,i,d in CASES if s==256 and i==d and i], [1280,1320,1344,1408,1536])
        self.assertIn((256,259,517),CASES);self.assertIn((256,0,0),CASES)
    def test_refuse_home_build(self):
        with self.assertRaisesRegex(ValueError,'host /dev/shm'):validate_paths(Path('/tmp/a'),Path('/home/coyang/new'))
    def test_refuse_volatile_evidence(self):
        with self.assertRaisesRegex(ValueError,'durable'):validate_paths(Path('/dev/shm/newcase'),Path('/dev/shm/evcase'))
    def test_no_retry(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError,'no retries'):validate_paths(Path('/dev/shm/never-start-geometry'),Path(d))

if __name__=='__main__':unittest.main()
