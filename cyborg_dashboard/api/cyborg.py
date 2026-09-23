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

# Cyborg reads OpenStack-API-Version as a bare "<major>.<minor>" (since
# upstream change 279a260, bug 2049489). An "accelerator 2.2" value fails
# to parse and Cyborg silently falls back to 2.0, so send the number alone.
API_VERSION = "2.0"

# Cyborg's MINOR_2_DP_BY_NAME: the first microversion whose device profile
# get_one accepts a name as well as a uuid.
DEVICE_PROFILE_BY_NAME_VERSION = "2.2"


class Adapter(adapter.LegacyJsonAdapter):
    def __init__(self, *args, **kwargs):
        self.api_version = kwargs.pop('api_version', None)
        super().__init__(*args, **kwargs)

    def request(self, url, method, **kwargs):
        kwargs.setdefault('headers', kwargs.get('headers', {}))
        if self.api_version is not None:
            # A call that needs a newer microversion passes its own header.
            kwargs['headers'].setdefault('OpenStack-API-Version',
                                         self.api_version)
        resp, body = super().request(url, method, **kwargs)
        return resp, body


@memoized
def make_adapter(request):
    auth = identity.Token(
        auth_url=base.url_for(request, 'identity'),
        token=request.user.token.id,
        project_id=request.user.project_id,
        project_name=request.user.project_name,
        project_domain_id=request.user.domain_id,
    )
    verify = True
    if settings.OPENSTACK_SSL_NO_VERIFY:
        verify = False
    elif settings.OPENSTACK_SSL_CACERT:
        verify = settings.OPENSTACK_SSL_CACERT
    return Adapter(
        session.Session(auth=auth, verify=verify),
        api_version=API_VERSION,
    )


def _url(request, path):
    base_uri = base.url_for(request, 'accelerator')
    return base_uri.rstrip('/') + '/' + path.lstrip('/')


def _get_json(request, path, headers=None):
    client = make_adapter(request)

    # LegacyJsonAdapter already decodes the payload; re-parsing the raw
    # response would blow up on an empty body (e.g. HTTP 204).
    _response, body = client.get(_url(request, path), headers=headers or {})
    return body if isinstance(body, dict) else {}


def _get_list(request, path, key):
    """Fetch ``path`` and return ``body[key]``, normalised to a list.

    ``dict.get(key, [])`` only defaults when the key is absent, so an
    explicit ``{"devices": null}`` would leak a None to the caller.

    No marker/limit handling: the Cyborg v2 ``get_all`` controllers for
    devices, deployables and ARQs take filters only and return the full
    collection, so there is no pagination to follow.
    """
    result = _get_json(request, path)
    return result.get(key) or []


def device_list(request):
    """List accelerator devices (FPGA, GPU, etc.) from Cyborg API."""
    return _get_list(request, 'devices', 'devices')


def device_profile_list(request):
    """List device profiles from Cyborg API."""
    return _get_list(request, 'device_profiles', 'device_profiles')


def device_profile_get(request, uuid_or_name):
    """Return a single device profile by uuid or name.

    get_one answers ``{"device_profile": {...}}``: a singular key holding
    one object, unlike the list call. Cyborg looks a profile up by name
    only from microversion 2.2 and answers 406 below it, so this call asks
    for 2.2 instead of the adapter's 2.0. An unknown profile raises the
    404 from Cyborg, as the other calls do for their errors.
    """
    body = _get_json(request, 'device_profiles/%s' % uuid_or_name,
                     headers={'OpenStack-API-Version':
                              DEVICE_PROFILE_BY_NAME_VERSION})
    return body.get('device_profile')


def device_profile_create(request, device_profile):
    """Create a single device profile.

    ``device_profile`` is a dict like::

        {"name": "fpga-dp",
         "groups": [{"resources:FPGA": "1",
                     "trait:CUSTOM_FPGA_INTEL": "required"}],
         "description": "..."}   # description optional

    The Cyborg v2 POST body is a list and the service rejects anything other
    than exactly one entry, so the single profile is wrapped here.
    """
    client = make_adapter(request)
    _response, body = client.post(_url(request, 'device_profiles'),
                                  json=[device_profile])
    return body


def device_profile_delete(request, uuid_or_name):
    """Delete a device profile by uuid or name."""
    client = make_adapter(request)
    client.delete(_url(request, 'device_profiles/%s' % uuid_or_name))


def accelerator_request_list(request):
    """List accelerator requests (ARQs) - accelerators bound to instances."""
    return _get_list(request, 'accelerator_requests', 'arqs')


def deployable_list(request):
    """List deployables linking devices to resource providers."""
    return _get_list(request, 'deployables', 'deployables')
