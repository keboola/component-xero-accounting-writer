import logging
from http.client import RemoteDisconnected
from typing import Dict, List, Optional

from keboola.component.dao import OauthCredentials
from ratelimit import limits, sleep_and_retry
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from urllib3.exceptions import ProtocolError
from xero_python.api_client import ApiClient
from xero_python.api_client.configuration import Configuration
from xero_python.api_client.oauth2 import OAuth2Token
from xero_python.api_client.serializer import serialize
from xero_python.exceptions.http_status_exceptions import HTTPStatusException, OAuth2InvalidGrantError
from xero_python.identity import IdentityApi

CALLS_PER_MINUTE = 50
ONE_MINUTE = 60


class XeroException(Exception):
    pass


class XeroClient:
    def __init__(self, oauth_credentials: OauthCredentials) -> None:
        self._oauth_token_dict: Dict = oauth_credentials.data

        oauth2_token_obj = OAuth2Token(
            client_id=oauth_credentials.appKey,
            client_secret=oauth_credentials.appSecret,
        )
        oauth2_token_obj.update_token(**self._oauth_token_dict)

        self._api_client = ApiClient(
            Configuration(oauth2_token=oauth2_token_obj),
            oauth2_token_getter=self.get_xero_oauth2_token_dict,
            oauth2_token_saver=self._set_xero_oauth2_token_dict,
        )
        self._available_tenant_ids: Optional[List[str]] = None

    def get_xero_oauth2_token_dict(self) -> Dict:
        return self._oauth_token_dict

    def _set_xero_oauth2_token_dict(self, new_token: Dict) -> None:
        self._oauth_token_dict = new_token

    @property
    def api_client(self) -> ApiClient:
        return self._api_client

    @retry(
        wait=wait_exponential(multiplier=1, min=4, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((HTTPStatusException, ProtocolError, RemoteDisconnected)),
    )
    def force_refresh_token(self) -> None:
        try:
            logging.info("Refreshing OAuth2 token")
            self._api_client.refresh_oauth2_token()
        except (HTTPStatusException, ProtocolError) as error:
            raise XeroException("Failed to authenticate the client, please reauthorize the component") from error

    def get_available_tenant_ids(self) -> List[str]:
        if not self._available_tenant_ids:
            self._refresh_available_tenant_ids()
        return self._available_tenant_ids  # type: ignore[return-value]

    def _refresh_available_tenant_ids(self) -> None:
        identity_api = IdentityApi(self._api_client)
        available_tenants: List[str] = []
        try:
            for connection in identity_api.get_connections():
                tenant = serialize(connection)
                available_tenants.append(tenant.get("tenantId"))
        except (OAuth2InvalidGrantError, HTTPStatusException) as oauth_err:
            raise XeroException(oauth_err) from oauth_err
        self._available_tenant_ids = available_tenants
        logging.info(f"Available tenant IDs: {self._available_tenant_ids}")

    @sleep_and_retry
    @limits(calls=CALLS_PER_MINUTE, period=ONE_MINUTE)
    def rate_limited_api_call(self, fn, *args, **kwargs):
        """Execute any AccountingApi call subject to rate limiting."""
        return fn(*args, **kwargs)
