import unittest
from datetime import datetime
from unittest.mock import Mock
from reminder.rules import load_config, switch_action, light_actions

class SwitchTests(unittest.TestCase):
    def setUp(self):
        self.cfg=load_config()
        self.now=datetime(2026,9,16,16,10)
        self.rng=Mock()
        self.rng.choice.side_effect=lambda values: values[0]

    def test_equal_category_threshold_with_unequal_pool_sizes(self):
        tasks=[{'id':1,'text':'阅读 MATLAB 代码'}]
        for value, expected in [(0.0,1),(0.499999,1),(0.5,None),(0.999,None)]:
            self.rng.random.return_value=value
            chosen=switch_action(self.now,self.cfg,tasks,'另一动作','MATLAB代码',self.rng)
            self.assertEqual(chosen[1],expected)

    def test_single_task_and_duplicate_text_cannot_repeat(self):
        tasks=[{'id':1,'text':'阅读代码'},{'id':2,'text':'阅读代码'}]
        chosen=switch_action(self.now,self.cfg,tasks,'阅读代码','阅读代码',self.rng)
        self.assertIsNone(chosen[1])
        self.assertNotEqual(chosen[0],'阅读代码')

    def test_no_tasks_and_single_item_pool_still_changes(self):
        cfg={'generic_pool':['唯一动作']}
        chosen=switch_action(self.now,cfg,[],'唯一动作','代码',self.rng)
        self.assertNotEqual(chosen[0],'唯一动作')
        self.assertIsNone(chosen[1])

    def test_context_uses_task_then_schedule(self):
        self.assertIn('打开待看的代码文件，只看开头的一条注释。',light_actions(self.now,self.cfg,'阅读MATLAB仿真代码'))
        self.assertNotIn('打开已经选好的论文，只读标题，不另外搜索。',light_actions(self.now,self.cfg,'图论自学'))
        self.assertIn('打开上次的科研记录，只读最后一条。',light_actions(datetime(2026,9,16,20),self.cfg))
