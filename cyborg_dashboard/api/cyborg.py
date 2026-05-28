#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

from django.conf import settings
from keystoneauth1 import adapter
from keystoneauth1 import identity
from keystoneauth1 import session

from openstack_dashboard.api import base

from horizon.utils.memoized import memoized


class Adapter(adapter.LegacyJsonAdapter):
    def __init__(self, *args, **kwargs):
        self.api_version = kwargs.pop('api_version', None)
        super().__init__(*args, **kwargs)

    def request(self, url, method, **kwargs):
        kwargs.setdefault('headers', kwargs.get('headers', {}))
        if self.api_version is not None:
            kwargs['headers']['OpenStack-API-Version'] = self.api_version
        resp, body = super().request(url, method, **kwargs)
        return resp, body


@memoized
def make_adapter(request):
    auth = identity.Token(
        auth_url=base.url_for(request, 'identity'),
        token=request.user.token.id,
        project_id=request.user.project_id,
        project_name=request.user.project_name,
        project_domain_name=request.user.domain_id,
    )
    verify = True
    if settings.OPENSTACK_SSL_NO_VERIFY:
        verify = False
    elif settings.OPENSTACK_SSL_CACERT:
        verify = settings.OPENSTACK_SSL_CACERT
    return Adapter(
        session.Session(auth=auth, verify=verify),
        api_version="accelerator 2.0",
    )


def _get_json(request, path):
    adapter = make_adapter(request)

    base_uri = base.url_for(request, 'accelerator')
    new_uri = base_uri.rstrip('/') + '/' + path.lstrip('/')

    response, body = adapter.get(new_uri)
    return response.json()


def device_list(request):
    """List accelerator devices (FPGA, GPU, etc.) from Cyborg API."""
    result = _get_json(request, 'devices')
    return result.get('devices', [])


def device_profile_list(request):
    """List device profiles from Cyborg API."""
    result = _get_json(request, 'device_profiles')
    return result.get('device_profiles', [])


def accelerator_request_list(request):
    """List accelerator requests (ARQs) - accelerators bound to instances."""
    result = _get_json(request, 'accelerator_requests')
    return result.get('arqs', [])


def deployable_list(request):
    """List deployables - logical units linking devices to resource providers."""
    result = _get_json(request, 'deployables')
    return result.get('deployables', [])
