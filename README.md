# UC Custom Select

Custom `select` entities for Unfolded Circle Remote Two and Remote 3.

The integration exploits the stock `remote-ui` `Text.AutoText` / Qt `StyledText`
renderer: every option can contain an inline Base64 image and styled text. No
modified `remote-ui` or firmware is required.

Each Select option can execute a command on an entity that already exists on
the same Remote. Core REST access is provided by
[`unfurled`](https://github.com/JackJPowell/unfurled), while integration
lifecycle, persistence and setup are handled by
[`ucapi-framework`](https://github.com/JackJPowell/ucapi-framework).

## Features

- Create multiple independent custom Select entities.
- Configure each Select through the normal UC integration setup flow.
- Authenticate with the Remote Web Configurator PIN and automatically create a
  dedicated Core API key.
- The Web Configurator PIN is used only during setup and is never persisted.
- Existing Selects on the same Remote can reuse the stored Core API key without
  asking for the PIN again.
- Inline Base64 PNG, JPEG, GIF, WebP or SVG option images.
- Configurable icon size from 16 to 192 px.
- Qt-native inline image alignment: top, middle or bottom.
- Configurable spacing between image and option name.
- Option-name styling:
  - bold
  - italic
  - underline
  - color
  - Qt HTML font size 1-7, or `0` to retain the Remote's native size
- Pick the target from entities already configured on the Remote.
- Map each option to any Core entity `cmd_id`.
- Supply arbitrary command parameters as a JSON object.
- `select_first`, `select_last`, `select_next`, `select_previous` and direct
  option selection are supported.
- Configuration backup/restore comes from `ucapi-framework`.

## How the option is rendered

For an option named `Netflix` with a 96 px icon, the integration exposes a
Select option string equivalent to:

```html
<img src="data:image/png;base64,..." align="middle" width="96" height="96">&nbsp;&nbsp;<b>Netflix</b>
```

The exact StyledText string is also the Select option value, which is why the
integration performs the command mapping internally.

## Authentication

The user does not need to create or copy a Core API key manually.

On the first connection to a Remote, setup asks for the Remote's **Web
Configurator PIN**. Unfurled authenticates with the PIN and creates a dedicated
Core API key with the `admin` scope. Only that generated API key is persisted in
the integration configuration; the PIN is discarded immediately after key
creation.

The generated key receives a name such as:

```text
UC Custom Select a1b2c3
```

A random suffix prevents a repeated setup attempt from revoking a key that may
still be used by another configured Select.

When another Select is created for a Remote that already has a stored key, the
PIN field may be left blank and the existing key is reused. Entering the PIN
again intentionally creates a fresh dedicated key for that Select. Connecting
to a different Remote requires that Remote's Web Configurator PIN.

If a previously stored Core API key has been revoked on the Remote, run setup
again and enter the PIN to create a new one.

## Setup

During setup:

1. Enter the Remote address, for example `192.168.1.50` or
   `http://remote.local`.
2. On the first connection to that Remote, enter its Web Configurator PIN.
   The integration automatically creates and stores a Core API key. The PIN
   itself is not stored.
3. Define the Select name and identifier.
4. Choose how many options the Select should contain.
5. Configure icon size, alignment, spacing and option-name styling.
6. For every option:
   - enter its visible name;
   - paste a raw Base64 image or full `data:image/...;base64,...` URI;
   - choose an existing entity on the Remote;
   - enter the entity command ID;
   - enter the command parameters as JSON.

To create more Select entities, open the integration's configuration again and
choose **Create another Select**. When the new Select targets the same Remote,
the Web Configurator PIN can be left blank because the saved Core API key is
reused.

## Example: Apple TV app launcher

Assume Home Assistant exposes an Apple TV media player on the Remote.

For the Netflix option:

- **Option name:** `Netflix`
- **Target entity:** the existing Apple TV media-player entity
- **Command ID:** `media_player.select_source`
- **Parameters:**

```json
{"source":"Netflix"}
```

For an option displayed as `Playstation` while the underlying Apple TV source
is `PXPlay`:

```json
{"source":"PXPlay"}
```

The visible option name and the command parameters are independent.

## Base64 images

The image field accepts either:

```text
iVBORw0KGgoAAA...
```

or:

```text
data:image/png;base64,iVBORw0KGgoAAA...
```

The integration validates and canonicalizes the data before storing it. The
decoded image limit is 128 KiB per option. Small pre-scaled square images are
strongly recommended; 96x96 assets of only a few KiB work especially well.

The configured icon size changes the rendered `width` and `height`. It does not
resample the underlying Base64 asset.

## Command mapping

Commands are sent through the Remote Core API:

```text
PUT /api/entities/{entity_id}/command
```

with:

```json
{
  "entity_id": "...",
  "cmd_id": "...",
  "params": {}
}
```

The integration uses `unfurled.api.CoreAPI.put_entity_command()` for this.

Examples include:

| Entity | Command | Parameters |
| --- | --- | --- |
| Media player | `media_player.select_source` | `{"source":"Netflix"}` |
| Activity | `activity.on` | `{}` |
| Remote | `remote.send_cmd` | `{"command":"HOME"}` |
| Select | `select_option` | `{"option":"Some option"}` |

Any command accepted by the target entity can be used; the integration does
not hard-code an allowlist.

## Current-option state

This is a generic command launcher, so there is no universal way to infer which
option is currently active from the target entities. The Select therefore
tracks the last successfully executed option for the lifetime of the
integration process. After a restart it initially points at the first option.

## Running with Docker

```bash
docker compose up -d --build
```

The container uses host networking for straightforward Remote discovery and
integration communication. Persistent configuration is stored in `./config`.

## Local development

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e . pytest pytest-asyncio ruff
ruff check .
pytest
python -m uc_intg_custom_select
```

## Security notes

- The Web Configurator PIN is used only to authenticate the API-key creation
  request and is never written to the integration configuration.
- The generated Core API key is persisted in the integration configuration.
- Configuration backups therefore contain the generated API key and should be
  treated as secrets.
- Base64 image data is also part of the entity attributes sent to the Remote.
- `ucapi-framework` setup DEBUG logging is explicitly disabled by this
  integration so PINs and pasted Base64 payloads are not dumped through its raw
  `UserDataResponse` debug logging.

## License

MPL-2.0
