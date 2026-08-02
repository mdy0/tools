"""Thin HTTP client for the Mailchimp Marketing API.

One class owns auth, base URL derivation, and response handling. Everything that talks to
Mailchimp — asset uploads, template patches, campaign creation, section writes — goes through
this client rather than calling `requests` directly, so the safety guard below applies uniformly.

Auth is HTTP Basic, any username, the API key as password. The key is never logged: not in
exceptions, not in a --dry-run dump. `MailchimpAPIError` messages include the response body,
which is Mailchimp's own text and never contains the key back.
"""

import base64
import os
import re
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent

# Never call these. Any request path matching this pattern raises in _request before any HTTP
# call happens — this is a real tripwire, not a comment.
#
# The pattern matches /actions/(send|test|resume|schedule) anywhere in the path -- not anchored
# to /campaigns/{id}/, and not an exact-path enumeration: that's deliberate belt-and-braces
# against a future endpoint shape (versioning, a different resource entirely) slipping past a
# too-precise regex. This tool only ever calls /campaigns, /templates, /file-manager, and /lists
# endpoints, so the broader match costs nothing today; a false positive costs a code change, a
# false negative can send an email that cannot be recalled — bias hard against the latter.
#
# `resume` (resumes a paused RSS campaign) is included for the same reason: this tool only ever
# creates regular draft campaigns and will never call it, but over-blocking costs one word.
# `schedule` is blocked permanently, no exceptions: this tool creates drafts and stops there — the
# human schedules the send in the Mailchimp UI.
_FORBIDDEN_PATTERN = re.compile(r'/actions/(send|test|resume|schedule)\b')


class MailchimpAPIError(RuntimeError):
    """Raised on any non-2xx response. Carries Mailchimp's own error body,
    which never contains the API key.
    """


class ForbiddenRequestError(RuntimeError):
    """Raised before any HTTP call for a path matching _FORBIDDEN_PATTERN --
    send, schedule, test-send, and resume are never allowed, no exceptions.
    """


class MailchimpClient:
    def __init__(self, env_path: Optional[Path] = None):
        load_dotenv(env_path or SCRIPT_DIR / '.env')
        key = os.getenv('MAILCHIMP_API_KEY')
        if not key:
            raise RuntimeError('MAILCHIMP_API_KEY not found in .env')
        if '-' not in key:
            raise RuntimeError('MAILCHIMP_API_KEY has no data-center suffix (expected e.g. ...-us1)')
        dc = key.rsplit('-', 1)[1]
        self._base = f'https://{dc}.api.mailchimp.com/3.0'
        self._auth = ('anystring', key)
        self.dc = dc

    def _request(self, method: str, path: str, json=None, params=None) -> dict:
        path_only = path.split('?', 1)[0]
        if _FORBIDDEN_PATTERN.search(path_only):
            raise ForbiddenRequestError(
                f'{method} {path} is forbidden -- never send, schedule, test-send, or resume a campaign'
            )
        r = requests.request(method, f'{self._base}{path}', auth=self._auth,
                              json=json, params=params, timeout=30)
        if r.status_code >= 400:
            try:
                detail = r.json()
            except ValueError:
                detail = r.text
            raise MailchimpAPIError(f'{method} {path} -> HTTP {r.status_code}: {detail}')
        if not r.content:
            return {}
        return r.json()

    def get(self, path: str, params=None) -> dict:
        return self._request('GET', path, params=params)

    def post(self, path: str, payload: dict) -> dict:
        return self._request('POST', path, json=payload)

    def put(self, path: str, payload: dict) -> dict:
        # Never a bare {'html': ...} payload on /campaigns/{id}/content -- it returns HTTP 200
        # and silently wipes the campaign body. See API-NOTES.md. This client doesn't
        # special-case that path; the caller must not build it (mailchimp_campaign.write_sections
        # never does).
        return self._request('PUT', path, json=payload)

    def patch(self, path: str, payload: dict) -> dict:
        return self._request('PATCH', path, json=payload)

    def delete(self, path: str) -> dict:
        return self._request('DELETE', path)

    # -- File Manager -------------------------------------------------------

    def _iter_files(self):
        """Page through every File Manager entry. The API has no
        search-by-name endpoint, so any name-based lookup pages through the
        full list and filters client-side.
        """
        offset = 0
        count = 1000  # the API's own page-size ceiling
        while True:
            page = self.get('/file-manager/files', params={
                'count': count, 'offset': offset,
                'fields': 'files.id,files.name,files.full_size_url,files.size,total_items',
            })
            files = page.get('files', [])
            for f in files:
                yield f
            offset += count
            if offset >= page.get('total_items', 0):
                return

    def find_files_by_stem(self, name: str) -> list:
        """Find every file in the same reuse "family" as `name`: the exact
        name itself, or Mailchimp's own suffixed-duplicate form
        `stem.NN.ext` (a re-upload under a name that's already taken doesn't
        overwrite -- it lands as `stem.01.ext`, `stem.02.ext`, etc, so
        matching only the exact original name means a reuse check could never
        see, and never converge on, whichever copy in the family actually has
        the current bytes).
        """
        stem = Path(name).stem
        suffix = Path(name).suffix
        pattern = re.compile('^' + re.escape(stem) + r'(\.\d+)?' + re.escape(suffix) + '$')
        return [f for f in self._iter_files() if pattern.match(f.get('name', ''))]

    def upload_file(self, name: str, data: bytes) -> dict:
        payload = {'name': name, 'file_data': base64.b64encode(data).decode()}
        return self.post('/file-manager/files', payload)

    def delete_file(self, file_id) -> None:
        self.delete(f'/file-manager/files/{file_id}')
