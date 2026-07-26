# Registers the native messaging host with Chrome on Windows (spec section 9).
# NOT YET FUNCTIONAL — host.py and com.securitycopilot.host.json are still
# stubs/templates. Fill those in first (spec section 15, build order step 9),
# then this script's job is: write com.securitycopilot.host.json somewhere
# stable, rewrite its "path" to an absolute path, fill in the real extension
# ID in "allowed_origins", and register
#   HKEY_CURRENT_USER\Software\Google\Chrome\NativeMessagingHosts\com.securitycopilot.host
# pointing at that manifest file's path.

Write-Error "Not yet implemented -- see this script's header comment and spec section 9."
exit 1
