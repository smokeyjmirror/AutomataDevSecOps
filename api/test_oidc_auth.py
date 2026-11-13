import base64
import hashlib
import unittest
import time
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from oidc_auth import OIDCConfig


def oidc_config():
    return OIDCConfig(
        issuer='https://identity.example/realms/automata',
        discovery_url='https://identity.example/realms/automata/.well-known/openid-configuration',
        client_id='automata-app',
        redirect_uri='http://localhost:5000/auth/callback',
        authorization_endpoint='',
        token_endpoint='',
        jwks_uri='',
        logout_endpoint='',
        client_secret=None,
        roles_claim='roles',
        customer_role='customer',
        staff_role='staff',
        email_claim='email',
        email_verified_claim='email_verified',
        scope='openid profile email',
        token_auth_method='client_secret_basic',
    )


class OIDCAuthTests(unittest.TestCase):
    def test_authorization_url_uses_state_nonce_and_pkce_s256(self):
        config = oidc_config()
        url, login_state = config.authorization_url(
            {'authorization_endpoint': 'https://identity.example/authorize'},
            config.redirect_uri,
        )
        params = parse_qs(urlsplit(url).query)
        expected_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(login_state['code_verifier'].encode('ascii')).digest()
        ).rstrip(b'=').decode('ascii')

        self.assertEqual(params['response_type'], ['code'])
        self.assertEqual(params['state'], [login_state['state']])
        self.assertEqual(params['nonce'], [login_state['nonce']])
        self.assertEqual(params['code_challenge'], [expected_challenge])
        self.assertEqual(params['code_challenge_method'], ['S256'])

    def test_logout_url_uses_provider_endpoint_and_allowed_return_uri(self):
        config = oidc_config()
        url = config.logout_url(
            {'end_session_endpoint': 'https://identity.example/logout'},
            'http://localhost:8000',
        )

        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params['client_id'], ['automata-app'])
        self.assertEqual(params['post_logout_redirect_uri'], ['http://localhost:8000'])

    @patch('oidc_auth.requests.get')
    def test_discovery_checks_issuer_and_applies_endpoint_overrides(self, get):
        config = oidc_config()
        config = OIDCConfig(
            **{
                **config.__dict__,
                'authorization_endpoint': 'http://localhost:8080/authorize',
                'token_endpoint': 'http://keycloak:8080/token',
                'jwks_uri': 'http://keycloak:8080/certs',
            }
        )
        response = Mock()
        response.json.return_value = {
            'issuer': config.issuer,
            'authorization_endpoint': 'https://identity.example/authorize',
            'token_endpoint': 'https://identity.example/token',
            'jwks_uri': 'https://identity.example/certs',
        }
        get.return_value = response

        metadata = config.load_metadata()

        response.raise_for_status.assert_called_once()
        self.assertEqual(metadata['authorization_endpoint'], 'http://localhost:8080/authorize')
        self.assertEqual(metadata['token_endpoint'], 'http://keycloak:8080/token')
        self.assertEqual(metadata['jwks_uri'], 'http://keycloak:8080/certs')

    @patch('oidc_auth.requests.get')
    def test_discovery_rejects_a_different_issuer(self, get):
        response = Mock()
        response.json.return_value = {'issuer': 'https://other.example'}
        get.return_value = response

        with self.assertRaisesRegex(ValueError, 'issuer'):
            oidc_config().load_metadata()

    @patch('oidc_auth.PyJWKClient')
    def test_validates_id_token_signature_audience_issuer_and_nonce(self, jwk_client):
        config = oidc_config()
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        jwk_client.return_value.get_signing_key_from_jwt.return_value.key = (
            private_key.public_key()
        )
        metadata = {
            'jwks_uri': 'https://identity.example/certs',
            'id_token_signing_alg_values_supported': ['RS256'],
        }
        claims = {
            'iss': config.issuer,
            'aud': config.client_id,
            'sub': 'user-123',
            'iat': int(time.time()),
            'exp': int(time.time()) + 3600,
            'nonce': 'expected-nonce',
            'roles': ['customer'],
            'email': 'ops@example.com',
            'email_verified': True,
        }
        token = jwt.encode(claims, private_key, algorithm='RS256')

        validated = config.validate_id_token(metadata, token, 'expected-nonce')

        self.assertEqual(validated['sub'], 'user-123')
        self.assertEqual(config.roles_from_claims(validated), ['customer'])
        self.assertEqual(config.email_from_claims(validated), 'ops@example.com')
        with self.assertRaises(jwt.InvalidTokenError):
            config.validate_id_token(metadata, token, 'wrong-nonce')

    def test_email_mapping_requires_verified_email(self):
        config = oidc_config()

        self.assertIsNone(
            config.email_from_claims(
                {'email': 'ops@example.com', 'email_verified': 'true'}
            )
        )
        self.assertEqual(
            config.email_from_claims(
                {'email': ' OPS@EXAMPLE.COM ', 'email_verified': True}
            ),
            'ops@example.com',
        )


if __name__ == '__main__':
    unittest.main()
