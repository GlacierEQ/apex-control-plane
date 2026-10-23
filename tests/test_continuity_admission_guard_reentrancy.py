"""Same-kernel reentrant recovery is denied without blocking other kernels."""
import threading
import unittest

from src import continuity_admission_guard as guard


class KernelAdmissionReentrancyTests(unittest.TestCase):
    def tearDown(self):
        self.assertEqual(guard._ACTIVE, {})

    def test_same_thread_reentry_denied_without_losing_outer_admission(self):
        kernel = object()
        with guard.exclusive_kernel_admission(kernel):
            with self.assertRaisesRegex(RuntimeError, "reentrant"):
                with guard.exclusive_kernel_admission(kernel):
                    self.fail("nested admission must not run")
            self.assertEqual(guard._ACTIVE[id(kernel)][3], threading.get_ident())
        with guard.exclusive_kernel_admission(kernel):
            pass

    def test_distinct_kernel_nested_admission_still_allowed(self):
        a, b = object(), object()
        with guard.exclusive_kernel_admission(a):
            with guard.exclusive_kernel_admission(b):
                pass

    def test_callback_exception_releases_admission(self):
        kernel = object()
        with self.assertRaises(ValueError):
            with guard.exclusive_kernel_admission(kernel):
                raise ValueError("host callback failed")
        with guard.exclusive_kernel_admission(kernel):
            pass

    def test_two_threads_serialize_on_same_kernel(self):
        kernel = object()
        entered = threading.Event()
        release = threading.Event()
        second_entered = threading.Event()

        def first():
            with guard.exclusive_kernel_admission(kernel):
                entered.set()
                release.wait(timeout=2)

        def second():
            entered.wait(timeout=2)
            with guard.exclusive_kernel_admission(kernel):
                second_entered.set()

        a = threading.Thread(target=first)
        b = threading.Thread(target=second)
        a.start()
        b.start()
        try:
            self.assertTrue(entered.wait(timeout=2))
            self.assertFalse(second_entered.wait(timeout=0.05))
        finally:
            release.set()
            a.join(timeout=2)
            b.join(timeout=2)
        self.assertFalse(a.is_alive())
        self.assertFalse(b.is_alive())
        self.assertTrue(second_entered.is_set())


if __name__ == "__main__":
    unittest.main()
