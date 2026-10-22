# Security

This experimental port uses an old downstream 3.10.108 kernel and a root-operated
desktop. There is no maintained-kernel security claim, screen lock or verified
suspend. Screen-off only blanks the display. See [status](docs/status.md).

Do not post secrets, identity files, raw boot/partition dumps, firmware or private
logs in public issues. After publication, use **Security → Report a vulnerability**
if private reporting is enabled; otherwise request a private channel without
disclosing the details. There is no published security support window yet.

Restrict maintenance access to USB/project-specific keys. SSH passwords and Groq
keys use private file permissions, not an encrypted vault. Tailscale does not
provide kernel maintenance or a screen lock.
