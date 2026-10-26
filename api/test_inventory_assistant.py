import unittest

from inventory_assistant import answer_inventory_query


INVENTORY = [
    {
        'sku': 'SEN-520',
        'name': 'Cargo Sensor',
        'quantity': 0,
        'reorder_point': 4,
        'target_stock': 16,
    },
    {
        'sku': 'CRY-210',
        'name': 'Cryo Cell',
        'quantity': 18,
        'reorder_point': 6,
        'target_stock': 24,
    },
    {
        'sku': 'SEAL-305',
        'name': 'Docking Seal',
        'quantity': 7,
        'reorder_point': 10,
        'target_stock': 30,
    },
    {
        'sku': 'FLT-100',
        'name': 'Nebula Filter',
        'quantity': 4,
        'reorder_point': 5,
        'target_stock': 20,
    },
    {
        'sku': 'CAB-440',
        'name': 'Quantum Cable',
        'quantity': 42,
        'reorder_point': 12,
        'target_stock': 48,
    },
]


class InventoryAssistantTests(unittest.TestCase):
    def test_answers_item_lookup_by_name(self):
        result = answer_inventory_query('How many Nebula Filters do we have?', INVENTORY)

        self.assertEqual([item['sku'] for item in result['items']], ['FLT-100'])
        self.assertIn('4 units in stock', result['answer'])
        self.assertIn('at or below its reorder point', result['answer'])

    def test_answers_item_lookup_by_sku(self):
        result = answer_inventory_query('Check CRY-210 stock', INVENTORY)

        self.assertEqual([item['sku'] for item in result['items']], ['CRY-210'])
        self.assertIn('18 units in stock', result['answer'])

    def test_lists_all_seeded_inventory(self):
        result = answer_inventory_query('Show me all inventory', INVENTORY)

        self.assertEqual(result['items'], INVENTORY)
        self.assertIn('Cargo Sensor (SEN-520): 0 in stock', result['answer'])
        self.assertIn('Quantum Cable (CAB-440): 42 in stock', result['answer'])

    def test_suggests_reorder_without_placing_order(self):
        result = answer_inventory_query('Which items are low in stock?', INVENTORY)

        self.assertEqual(
            [item['sku'] for item in result['items']],
            ['SEN-520', 'SEAL-305', 'FLT-100'],
        )
        self.assertIn('Cargo Sensor (SEN-520): 0 in stock', result['answer'])
        self.assertIn('Suggested reorder: 16 to reach the target of 16', result['answer'])
        self.assertIn('Docking Seal (SEAL-305): 7 in stock', result['answer'])
        self.assertIn('Suggested reorder: 23 to reach the target of 30', result['answer'])
        self.assertIn('Nebula Filter (FLT-100): 4 in stock', result['answer'])
        self.assertIn('Suggested reorder: 16 to reach the target of 20', result['answer'])
        self.assertIn('no orders were placed', result['answer'])

    def test_low_stock_question_can_target_a_specific_item(self):
        result = answer_inventory_query('Is Cryo Cell low in stock?', INVENTORY)

        self.assertEqual([item['sku'] for item in result['items']], ['CRY-210'])
        self.assertIn('above its reorder point', result['answer'])
        self.assertIn('no reorder is suggested', result['answer'])

    def test_does_not_guess_unknown_items(self):
        result = answer_inventory_query('How many warp drives do we have?', INVENTORY)

        self.assertEqual(result['items'], [])
        self.assertIn("couldn't identify", result['answer'])


if __name__ == '__main__':
    unittest.main()
