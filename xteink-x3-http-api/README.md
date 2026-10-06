# XTEiNK X3 eReader: HTTP API reference (unofficial)

This is a reference for anyone who wants to write their own tool that copies books to an XTEiNK X3 over Wi-Fi, instead of using the vendor's web page.

The contents were derived from reading the code of the vendor's web page, <http://bofi.xteink.com/index.html> (the device calls are in its `assets/pages-index-index.*.js` file), and then testing every call against a real device. Nothing here comes from the vendor's documentation.

**Page retrieved:** 2026-10-06. Its files were last modified by the vendor on 2026-02-05, before the device testing below, and still matched this document when re-checked. The vendor can change the page at any time without notice, so if a call here behaves differently, read the page's code again.

**Status.** Tested on 2026-10-01 against one X3 running stock firmware `XT V6.3.15` (`device_type` `ESP32C3_X3`), from a MacBook, with Python's standard library and curl. Other firmware versions, and the community CrossPoint firmware, were not tested and may behave differently. Treat everything here as "worked on this one device", not as a guarantee.

All write tests were done inside a scratch folder that was deleted afterwards.

## Contents

- [How the device is reachable](#how-the-device-is-reachable)
- [Conventions](#conventions)
- [Endpoints](#endpoints)
- [Behaviour you need to know about](#behaviour-you-need-to-know-about)
- [File names](#file-names)
- [Speed and timeouts](#speed-and-timeouts)
- [How the eReader tracks books](#how-the-ereader-tracks-books)
- [Endpoints to avoid](#endpoints-to-avoid)
- [Examples](#examples)
- [Not tested](#not-tested)

## How the device is reachable

- **The device's web server only runs while the transfer screen is open.** On the eReader that is Settings, page 2, File Transfer, "Upload from Network (PC)". On any other screen, or when asleep, nothing answers. That is normal, not an error to debug.
- **It stops answering after a few idle minutes.** Requests time out and even ping fails. It does not recover by itself: the user has to back out of the transfer screen and open it again, after which it answers immediately. A single long upload (3 minutes) kept the screen alive, so it is idleness that stops it, not duration.
- **Wi-Fi is 2.4 GHz only.** USB-C does not transfer files.
- **There is no authentication.** Anyone on the same network can read, write and delete files while the screen is open.
- **Plain HTTP on port 80.** Port 443 refuses connections.
- **Host name:** the vendor page uses `http://e-paper.local` (mDNS). In testing it resolved once, taking about 5 seconds, and failed at other times. The IP address answered in about 0.15 s. Resolve the name once, then use the IP address for the rest of the run, and remember the last working IP as a fallback.
- **It behaves like a small ESP32:** one request at a time, slow, easily overwhelmed. Do not send requests in parallel.
- The API shape (`/list?dir=`, `/edit` with POST, PUT and DELETE) matches the well-known ESP32 Arduino SDWebServer / FSBrowser example.

## Conventions

- Every response carries `Connection: close` and permissive CORS headers. Open a new connection per request.
- Paths are absolute card paths starting with `/`. Folder paths used in `/list` end in `/`.
- When a path goes in a URL query string or a GET path, URL-encode it (keep `/` unescaped).
- Error bodies are plain text and sometimes in Chinese. **The HTTP status is reliable; do not parse the text.** The Chinese messages are quoted below only to help you recognise them.

## Endpoints

| Action | Request | Success | Notes |
|---|---|---|---|
| Status | `GET /status` | 200, JSON | Fast reachability check. |
| Name and IP | `GET /Read_staNameIp` | 200, plain text | Not useful for identifying the device (see below). |
| List a folder | `GET /list?dir=<path>` | 200, JSON array | One level only, unsorted. |
| Download a file | `GET /<path>` | 200, file bytes | Not used by the vendor page, but works. |
| Upload a file | `POST /edit` (multipart) | 200 | Overwrites an existing file. |
| Create a folder | `PUT /edit` (form field `path`) | 200 | Creates missing parents. |
| Move or rename | `PUT /edit` (fields `path`, `src`) | 200 | Files and folders. |
| Delete | `DELETE /edit?path=<path>` | 200 | Files and empty folders only. |

### GET /status

Returns `application/json`, for example:

```json
{"type":"SD","isOk":"true","id":"1234567","device_type":"ESP32C3_X3","version":"XT V6.3.15","totalBytes":1.599123692e10,"usedBytes":2333}
```

- **`totalBytes` and `usedBytes`** are numbers (the first is in scientific notation).
- **`id`** looks like a hardware ID but I did not rely on it.
- **Use it as the "is the eReader there?" check.** The vendor page treats any 2xx as connected, with a 5 second timeout. Retry once before concluding the screen is closed.

### GET /Read_staNameIp

Returns plain text: two whitespace-separated words, for example `MyWifiName 192.168.1.50`. The first word is the **Wi-Fi network name, not a device name**, so it cannot tell two eReaders apart. The second is the device's IP address. The vendor page uses it to learn the IP after resolving `e-paper.local`.

### GET /list?dir=\<path\>

```
GET /list?dir=/Pushed%20Books/
```

Returns a JSON array (content type `text/json`, chunked):

```json
[{"type":"dir","size":"0","name":"Some Author"},{"type":"file","size":"485312","name":"A Book.epub"}]
```

- **`type`** is `"dir"` for folders. Treat anything else as a file.
- **`size` is a string**, and folders report `"0"`.
- **There are no dates and no checksums.** The only way to detect a changed file is a size difference.
- **It is not recursive and not sorted.** Walk folders yourself.
- **Listing a folder that does not exist returns `[]` with HTTP 200**, exactly like an empty folder. To test whether a folder exists, list its parent and look for it.
- **Hidden entries:** `XTCache`, `System Volume Information` and `.fseventsd` are not listed. `.Spotlight-V100`, `.TemporaryItems` and macOS `._*` AppleDouble files (4096 bytes, beside some books) are listed. Filter these out yourself.

### GET /\<path\>

```
GET /Pushed%20Books/A%20Book.epub
```

Returns the file bytes, byte-identical to what is on the card (tested at 63 B, 485 KB and 4 MB), at about 130 KB/s. A missing file gives 404. It also works on the hidden `XTCache` files, which is useful for reading reading-progress data but must be treated as read-only.

### POST /edit (upload)

A standard `multipart/form-data` body with **one file part named `data`, whose `filename` is the full destination path**, not just the file name.

```
POST /edit HTTP/1.1
Content-Type: multipart/form-data; boundary=XYZ
Content-Length: ...

--XYZ
Content-Disposition: form-data; name="data"; filename="/Pushed Books/A Book.epub"
Content-Type: application/octet-stream

<file bytes>
--XYZ--
```

- **The path must start with `/`.**
- **The destination folder must already exist.** Uploading into a missing folder fails with HTTP 500 `Creation failed <path>`. Create folders first.
- **Uploading to an existing path overwrites it.** Size and content are replaced; no delete is needed first.
- **Raw UTF-8 in the quoted `filename` is accepted**, including spaces and non-ASCII characters. Escape only `"` (as `%22`) and backslash.
- **There is no chunking or resume.** The vendor page sends the whole file in one request, and so does the tool. If a transfer is cut off, the partial file may be left on the card, so list the folder afterwards and compare sizes. Re-uploading over it is safe.
- **Stream the body** (send the multipart head, then the file in blocks, then the tail, with an exact `Content-Length`) rather than building it in memory. In Python, `urllib` cannot do this with progress reporting; `http.client.HTTPConnection` can.

### PUT /edit (create folder)

A multipart form body (this is what was tested) with one field, `path`, ending in `/`:

```
path=/Pushed Books/Some Author/
```

Creates the folder and any missing parents in one call. Returns 200.

### PUT /edit (move or rename)

Form fields `path` = the new path and `src` = the old path:

```
path=/Pushed Books/Some Author/A Book.epub
src=/Pushed Books/A Book.epub
```

| Case | Result |
|---|---|
| File to another existing folder | 200 |
| Whole folder | 200 (give `path` and `src` without a trailing slash) |
| Destination folder missing | 500 `重命名失败` ("rename failed"). Create it first. |
| Destination file already exists | 400 `路径下有同名文件` ("a file with that name exists"). **Nothing is overwritten.** |
| `src` missing | 400 `找不到SRC文件` ("SRC file not found") |

### DELETE /edit?path=\<path\>

```
DELETE /edit?path=/Pushed%20Books/A%20Book.epub
```

| Case | Result |
|---|---|
| File | 200 |
| Empty folder | 200 |
| Missing path | 404 `文件不存在` ("file does not exist") |
| Folder with anything inside | 500 "When there are files in a folder, it is not possible to delete the folder". Delete the contents first. |

## Behaviour you need to know about

- **Creating, moving and uploading go folder-first.** Create the folder, then move or upload into it. Both fail if the folder is missing.
- **Verify every write by listing the parent folder** and checking the size. A 200 on upload is not proof the file is whole if the connection dropped late.
- **A moved file onto an existing name is refused, not replaced.** That makes "move" a safe operation.
- **Leaving the transfer screen re-indexes the library.** A book uploaded over Wi-Fi appeared in the library after the user backed out of the transfer screen. There is no re-index endpoint and none is needed.
- **A book with no cover image** shows "cover format not supported" on first open. Harmless.
- **Dot files do not appear in the eReader's own folder view**, so a hidden marker file such as `.my-tool-<id>` in the card root is invisible to the reader but visible to `/list`. This is a handy way to give a card an identity of its own, because the device has no usable name or serial.
- **Wallpapers:** in a copy of one card, only 528x792, 24-bit BMP files dithered to 4 grey levels worked as wallpaper, and PNG silently failed. This came from the card's contents, not from an API test.

## File names

- `&`, apostrophes, `é`, `–`, `Ü`, Japanese, commas, parentheses, square brackets, `#` and `%` all survived upload, listing and download.
- **Unicode normalisation is stored exactly as sent.** A name in NFD form (`e` plus a combining accent, which is what macOS often produces) is stored and listed as NFD. **Normalise every path to NFC before comparing or uploading**, or the same book can end up on the card twice under names that look identical.
- The card itself is FAT-style. If you compare names between your computer and the card, compare case-insensitively.

## Speed and timeouts

- **Upload:** 1 MB took 7.6 s (about 135 KB/s); 10 MB took 171 s (about 60 KB/s). Throughput drops on larger files.
- **Download:** about 130 KB/s.
- **Suggested timeouts:** 5 s for `/status` and `/list`; for an upload, 60 s plus file size divided by 20 KB/s.
- Show progress. A 10 MB book takes close to three minutes and looks hung without it.
- If a request times out, stop cleanly and tell the user to back out of the transfer screen and open it again, then re-run. Retrying in a loop will not help.

## How the eReader tracks books

This matters if your tool moves or renames books. It was read from a copy of the card and confirmed on the device.

- Per-book data (reading position, unpacked book, cover, read time) is keyed by the **file name without its extension**, not by the path. It lives under `XTCache/` on the card, for example `XTCache/epub/<name>/progress.txt`.
- **Moving a book to another folder, keeping its file name, keeps the reading position.**
- **Renaming a book loses the reading position.** The renamed book is indexed again and opens at the start. The old cache entry is left behind, harmless.
- **The reader reopens a book where you last were,** not at the furthest point you reached.
- `XTCache/BCID/...` holds an identity record per book (type, name, a content fingerprint, the path when first seen, size, time). It is not updated when a book is moved or renamed.
- **Never write to `XTCache/`.** It is the device's own data. Reading it over the download call is fine.

## Endpoints to avoid

The vendor page also exposes device settings. A sync tool has no reason to call these, and one is actively harmful:

- **`POST /Put_sdInit`:** toggles the SD card state every time it is called. Do not call it.
- **`POST /Put_sdFrequency`, `POST /webPut_longPress`:** change device settings.
- **`GET /Read_updataAddress`:** the firmware update address.
- **`/Read_sdInit`, `/Read_sdFrequency`, `/webRead_longPress`:** read-only and harmless, but also unnecessary.

I did not probe for other endpoints by guessing. Everything above is either in the vendor page's code or was seen working.

## Examples

### curl

Set the IP first (find it on your router, or from `/Read_staNameIp`):

```
X3=192.168.1.50

curl -s -m 5 http://$X3/status
curl -s -m 5 "http://$X3/list?dir=/"
curl -s -m 5 "http://$X3/list?dir=/Pushed%20Books/"

# Create a folder
curl -s -X PUT -F 'path=/Pushed Books/Some Author/' http://$X3/edit

# Upload (note: the filename is the full destination path)
curl -s -F 'data=@A Book.epub;filename=/Pushed Books/Some Author/A Book.epub' http://$X3/edit

# Move
curl -s -X PUT -F 'path=/Pushed Books/Other/A Book.epub' -F 'src=/Pushed Books/Some Author/A Book.epub' http://$X3/edit

# Download
curl -s -o "A Book.epub" "http://$X3/Pushed%20Books/Other/A%20Book.epub"

# Delete
curl -s -X DELETE "http://$X3/edit?path=/Pushed%20Books/Other/A%20Book.epub"
```

### Python (standard library only)

A minimal streaming upload, the part `urllib` cannot do:

```python
import http.client, os, secrets, unicodedata

def upload(ip, local_path, dest, block=16384):
    dest = unicodedata.normalize("NFC", dest)          # see "File names"
    size = os.path.getsize(local_path)
    boundary = "x" + secrets.token_hex(8)
    quoted = dest.replace("\\", "\\\\").replace('"', "%22")
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="data"; '
            f'filename="{quoted}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
    tail = f"\r\n--{boundary}--\r\n".encode()
    conn = http.client.HTTPConnection(ip, 80, timeout=60 + size / 20000)
    conn.putrequest("POST", "/edit")
    conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
    conn.putheader("Content-Length", str(len(head) + size + len(tail)))
    conn.endheaders()
    conn.send(head)
    with open(local_path, "rb") as f:
        while chunk := f.read(block):
            conn.send(chunk)
    conn.send(tail)
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp.status        # 200 on success; then list the folder and check the size
```

## Not tested

- Encoding conversion for `.txt` files. The vendor page detects the encoding in the browser and converts before uploading; EPUB needs no conversion and is the main case.
- Responses when the SD card is busy or unavailable.
- Any re-index endpoint (none is known, and I did not guess at endpoints).
- Other firmware versions, other XTEiNK models, and the CrossPoint community firmware.
- Several readers on one network at once (the `/Read_staNameIp` name is the Wi-Fi network, so tell them apart by IP, or by a marker file you place on the card).

## Source

The calls above were read from the vendor's own web page (the device calls are all in its app logic file, on one object, with Chinese console labels such as `[list]`, `[upload]`, `[delete]`, `[rename]`, `[createFolder]`) and then each one was tried against a real device. This document is unofficial and not affiliated with or endorsed by XTEiNK. Use it at your own risk: the API has no authentication and can delete files on the card.
