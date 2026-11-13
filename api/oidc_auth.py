import base64
import hashlib
import os
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import jwt
import requests
from jwt import PyJWKClient


@dataclass(frozen=True)
class OIDCConfig:
    issuer: str
    discovery_url: str
    client_id: str
    redirect_uri: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    logout_endpoint: str
    client_secret: str | None
    roles_claim: str
    customer_role: str
    staff_role: str
    email_claim: str
    email_verified_claim: str
    scope: str
    token_auth_method: str

    @classmethod
    def from_env(cls):
        issuer = os.environ.get('OIDC_ISSUER', '')
        return cls(
            issuer=issuer,
            discovery_url=os.environ.get(
                'OIDC_DISCOVERY_URL',
                f'{issuer}/.well-known/openid-configuration' if issuer else '',
            ),
            client_id=os.environ.get('OIDC_CLIENT_ID', ''),
            redirect_uri=os.environ.get(
                'OIDC_REDIRECT_URI', 'http://localhost:5000/auth/callback'
            ),
            authorization_endpoint=os.environ.get('OIDC_AUTHORIZATION_ENDPOINT', ''),
            token_endpoint=os.environ.get('OIDC_TOKEN_ENDPOINT', ''),
            jwks_uri=os.environ.get('OIDC_JWKS_URI', ''),
            logout_endpoint=os.environ.get('OIDC_LOGOUT_ENDPOINT', ''),
            client_secret=os.environ.get('OIDC_CLIENT_SECRET') or None,
            roles_claim=os.environ.get('OIDC_ROLES_CLAIM', 'roles'),
            customer_role=os.environ.get('OIDC_CUSTOMER_ROLE', 'customer'),
            staff_role=os.environ.get('OIDC_STAFF_ROLE', 'staff'),
            email_claim=os.environ.get('OIDC_EMAIL_CLAIM', 'email'),
            email_verified_claim=os.environ.get('OIDC_EMAIL_VERIFIED_CLAIM', 'email_verified'),
            scope=os.environ.get('OIDC_SCOPE', 'openid profile email'),
            token_auth_method=os.environ.get('OIDC_TOKEN_AUTH_METHOD', 'client_secret_basic'),
        )

    @property
    def enabled(self):
        return bool(self.issuer and self.discovery_url and self.client_id)

    def load_metadata(self) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError('OIDC is not configured')

        response = requests.get(self.discovery_url, timeout=5)
        response.raise_for_status()
        metadata = response.json()
        if not isinstance(metadata, dict):
            raise ValueError('OIDC discovery document must be a JSON object')
        discovered_issuer = metadata.get('issuer')
        if not isinstance(discovered_issuer, str) or discovered_issuer != self.issuer:
            raise ValueError('OIDC discovery issuer does not match OIDC_ISSUER')

        metadata['authorization_endpoint'] = (
            self.authorization_endpoint or metadata.get('authorization_endpoint')
        )
        metadata['token_endpoint'] = self.token_endpoint or metadata.get('token_endpoint')
        metadata['jwks_uri'] = self.jwks_uri or metadata.get('jwks_uri')
        metadata['end_session_endpoint'] = (
            self.logout_endpoint or metadata.get('end_session_endpoint')
        )
        required_endpoints = (
            'authorization_endpoint',
            'token_endpoint',
            'jwks_uri',
        )
        if any(not metadata.get(endpoint) for endpoint in required_endpoints):
            raise ValueError('OIDC discovery metadata is missing required endpoints')
        return metadata

    def authorization_url(self, metadata: dict[str, Any], redirect_uri: str):
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode('ascii')).digest()
        ).rstrip(b'=').decode('ascii')
        params = {
            'client_id': self.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': self.scope,
            'state': state,
            'nonce': nonce,
            'code_challenge': challenge,
            'code_challenge_method': 'S256',
        }
        return (
            f"{metadata['authorization_endpoint']}?{urlencode(params)}",
            {'state': state, 'nonce': nonce, 'code_verifier': verifier},
        )

    def logout_url(self, metadata: dict[str, Any], redirect_uri: str):
        endpoint = metadata.get('end_session_endpoint')
        if not endpoint:
            return None
        params = {
            'client_id': self.client_id,
            'post_logout_redirect_uri': redirect_uri,
        }
        return f'{endpoint}?{urlencode(params)}'

    def exchange_code(self, metadata: dict[str, Any], code: str, verifier: str):
        if self.client_secret and self.token_auth_method not in {
            'client_secret_basic',
            'client_secret_post',
        }:
            raise ValueError('OIDC_TOKEN_AUTH_METHOD must be client_secret_basic or client_secret_post')
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.redirect_uri,
            'code_verifier': verifier,
        }
        auth = None
        if self.client_secret and self.token_auth_method == 'client_secret_basic':
            auth = (self.client_id, self.client_secret)
        else:
            data['client_id'] = self.client_id
            if self.client_secret:
                data['client_secret'] = self.client_secret

        response = requests.post(
            metadata['token_endpoint'],
            data=data,
            auth=auth,
            timeout=10,
        )
        response.raise_for_status()
        token_response = response.json()
        if not isinstance(token_response, dict) or not token_response.get('id_token'):
            raise ValueError('OIDC token response did not contain an ID token')
        return token_response

    def validate_id_token(self, metadata: dict[str, Any], encoded_token: str, nonce: str):
        signing_key = PyJWKClient(metadata['jwks_uri'], timeout=5).get_signing_key_from_jwt(
            encoded_token
        )
        supported_algorithms = metadata.get('id_token_signing_alg_values_supported', [])
        algorithms = [
            algorithm
            for algorithm in supported_algorithms
            if algorithm in {
                'RS256', 'RS384', 'RS512',
                'PS256', 'PS384', 'PS512',
                'ES256', 'ES384', 'ES512',
            }
        ]
        if not algorithms:
            raise ValueError('OIDC provider advertises no supported ID token signing algorithm')

        claims = jwt.decode(
            encoded_token,
            signing_key.key,
            algorithms=algorithms,
            audience=self.client_id,
            issuer=self.issuer,
            options={'require': ['exp', 'iat', 'sub', 'nonce']},
        )
        audience = claims.get('aud')
        if isinstance(audience, list) and len(audience) > 1:
            if claims.get('azp') != self.client_id:
                raise jwt.InvalidTokenError('OIDC ID token authorized party is invalid')
        elif claims.get('azp') not in (None, self.client_id):
            raise jwt.InvalidTokenError('OIDC ID token authorized party is invalid')
        if claims.get('nonce') != nonce:
            raise jwt.InvalidTokenError('OIDC ID token nonce does not match the login request')
        return claims

    def roles_from_claims(self, claims: dict[str, Any]):
        roles = claims.get(self.roles_claim, [])
        if isinstance(roles, str):
            return [roles]
        if isinstance(roles, list) and all(isinstance(role, str) for role in roles):
            return roles
        return []

    def email_from_claims(self, claims: dict[str, Any]):
        email = claims.get(self.email_claim)
        verified = claims.get(self.email_verified_claim)
        if not isinstance(email, str) or verified is not True:
            return None
        return email.strip().lower()
