"""Upload this run's banner image to the Mailchimp File Manager.

Network-touching, but only against /file-manager/files -- nothing here creates a campaign or
writes a template.
"""

from pathlib import Path

from mailchimp_client import MailchimpClient
from newsletter_markdown import ParsedNewsletter


class AssetError(ValueError):
    """Raised when the banner file is missing on disk. Preflight this before
    any upload -- an abort after some but not all assets have been pushed to
    the account is a worse failure mode than aborting up front.
    """


def resolve_asset_path(markdown_dir: Path, banner_path: str) -> Path:
    """Resolve **Banner:**'s path relative to the markdown file's own
    directory -- never the current working directory, and never a
    project-root guess. The markdown contract (FORMAT.md) pins this: a
    collector that writes a different newsletter-*.md file next to a
    different images/ directory still resolves correctly.

    Enforces that same contract, not just documents it: an absolute `banner_path` would replace
    `markdown_dir` entirely under plain pathlib semantics (`Path('/a') / '/etc/hosts'` is
    `/etc/hosts`), and a `../`-laden one can walk outside `markdown_dir` even though the joined
    path looks relative -- either way, a crafted markdown file could point this tool at any
    readable local file and have it uploaded to Mailchimp's File Manager. Both are refused here,
    before the file is ever touched.
    """
    if Path(banner_path).is_absolute():
        raise AssetError(
            f'**Banner:** must be a path relative to the markdown file\'s own directory, per '
            f'FORMAT.md -- got an absolute path: {banner_path!r}'
        )
    resolved_dir = markdown_dir.resolve()
    resolved_path = (markdown_dir / banner_path).resolve()
    if not resolved_path.is_relative_to(resolved_dir):
        raise AssetError(
            f'**Banner:** must stay within the markdown file\'s own directory, per FORMAT.md -- '
            f'{banner_path!r} resolves to {resolved_path}, outside {resolved_dir}'
        )
    return resolved_path


def preflight_banner(parsed: ParsedNewsletter, markdown_dir: Path) -> Path:
    """Resolve and confirm the banner file exists, before any network call."""
    path = resolve_asset_path(markdown_dir, parsed.banner_path)
    if not path.exists():
        raise AssetError(f'Banner file not found: {path}')
    return path


def upload_asset(client: MailchimpClient, path: Path) -> str:
    """Upload `path` to the File Manager and return its full_size_url. Not named `upload_file`
    (that's `MailchimpClient.upload_file`, the raw single-call upload this function wraps) --
    two functions with the same name in adjacent modules is exactly the mistake worth avoiding,
    since only this one does the reuse check below; a raw `client.upload_file` call skips it and
    grows the account by one file per re-run.

    Searches the reuse family for a same-size match first, so a re-run on
    the same file doesn't grow the account by one file per run.

    Reuse requires the same byte size. A stale entry under the exact
    original name is never deleted here -- these filenames may still be
    referenced by an already-created campaign, so deleting one could break
    an image in a draft (or, worse, mail already delivered). Instead every
    name in the family (`stem.ext`, `stem.01.ext`, `stem.02.ext`, ...) is
    searched for the one whose size matches the local file; if none
    matches, a fresh copy is uploaded and Mailchimp assigns it the next
    suffix in the family, and that upload is printed so growth stays
    visible rather than silent.
    """
    family = client.find_files_by_stem(path.name)
    local_size = path.stat().st_size
    for f in family:
        if f.get('size') == local_size:
            return f['full_size_url']
    if family:
        print(
            f'{path.name}: {len(family)} existing File Manager entr{"y" if len(family) == 1 else "ies"} '
            f'in this family, none matching {local_size} bytes -- uploading a fresh copy.'
        )
    result = client.upload_file(path.name, path.read_bytes())
    return result['full_size_url']
