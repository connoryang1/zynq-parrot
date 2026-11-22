"""Resource selection fixtures only; no actual source/model/reader execution."""
import unittest
import preflight as p


class PreflightTests(unittest.TestCase):
    def test_choose_prospectively_from_complete_occupied_pool(self):
        self.assertEqual(p.choose(500*1024**2),256*1024**2)
        self.assertEqual(p.choose(513*1024**2),128*1024**2)
        self.assertEqual(p.choose(640*1024**2),128*1024**2)
        with self.assertRaises(ValueError):p.choose(640*1024**2+1)

    def test_exact_new_model_only(self):
        self.assertEqual(p.b.MODEL_SHA,'6a4214d9b03574d0d0f75ab210e7c91dc447897eba5bee465965370a3dc433e0')
        self.assertNotIn('1e9519',p.b.MODEL_SHA)
        self.assertEqual(p.CAP,768*1024**2)
        self.assertEqual(p.DURABLE_SUBCAP,16*1024**2)


if __name__=='__main__':unittest.main()
