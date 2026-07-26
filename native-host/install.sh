#!/usr/bin/env bash
# Registers the native messaging host with Chrome on macOS/Linux (spec section 9).
# NOT YET FUNCTIONAL — host.py and com.securitycopilot.host.json are still
# stubs/templates. Fill those in first (spec section 15, build order step 9),
# then this script's job is: copy com.securitycopilot.host.json to Chrome's
# native-messaging-hosts directory for the current OS —
#   Linux:  ~/.config/google-chrome/NativeMessagingHosts/
#   macOS:  ~/Library/Application Support/Google/Chrome/NativeMessagingHosts/
# with the manifest's "path" rewritten to an absolute path, and "allowed_origins"
# filled in with the real extension ID.

echo "Not yet implemented — see this script's header comment and spec section 9." >&2
exit 1
