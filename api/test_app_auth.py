import unittest
from unittest.mock import MagicMock, patch

from app import app


class AppAuthTests(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-only'
        self.client = app.test_client()

    def authenticate(self, roles, email='ops@apexlabs.example'):
        with self.client.session_transaction() as browser_session:
            browser_session['identity'] = {
                'sub': 'user-123',
                'email': email,
                'roles': roles,
            }

    def test_job_list_requires_authentication(self):
        response = self.client.get('/jobs')

        self.assertEqual(response.status_code, 401)

    def test_customer_cannot_read_staff_client_list(self):
        self.authenticate(['customer'])

        response = self.client.get('/clients')

        self.assertEqual(response.status_code, 403)

    @patch('app.get_kafka_producer', return_value=None)
    @patch('app.get_db_connection')
    @patch('app.get_active_client_for_identity')
    def test_job_creation_uses_authenticated_client_not_payload(
        self, get_client, get_db_connection, _get_kafka_producer
    ):
        self.authenticate(['customer'])
        get_client.return_value = {'id': 7, 'company_name': 'Apex Labs'}
        cursor = MagicMock()
        cursor.fetchone.return_value = {'id': 42, 'client_id': 7, 'task': 'Review'}
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        get_db_connection.return_value.__enter__.return_value = connection

        response = self.client.post(
            '/jobs',
            json={
                'client_id': 999,
                'agent_id': 1,
                'task': 'Review',
                'duration_hours': 2,
            },
        )

        self.assertEqual(response.status_code, 201)
        insert_call = cursor.execute.call_args
        self.assertEqual(insert_call.args[1], (7, 1, 'Review', 2))
        get_client.assert_called_once()


if __name__ == '__main__':
    unittest.main()
