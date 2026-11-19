import unittest
from common_experiments import counter_experiment, cpu_work, queue_experiment


class ExperimentTests(unittest.TestCase):
    def test_lock_prevents_lost_updates(self):
        self.assertEqual(counter_experiment(False, 3, 10)['actual'], 10)
        self.assertEqual(counter_experiment(True, 3, 10)['actual'], 30)

    def test_queue_processes_every_item_once(self):
        values = [3, 5, 7, 9]
        self.assertEqual(queue_experiment(values), sorted(map(cpu_work, values)))


if __name__ == '__main__':
    unittest.main()
