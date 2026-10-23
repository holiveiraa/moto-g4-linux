# GitHub Wiki

The repository documentation works immediately through ordinary GitHub links.
The optional Wiki presents the same material as a browsable handbook, with Home,
sidebar, Hermes setup/server-agent tutorial, screenshots, terminal usage,
hardware matrix, installation, builds and troubleshooting.

GitHub keeps a Wiki in its **own Git repository**. Creating files under `wiki/`
in the source repository does not automatically publish them to the Wiki.
After the owner publishes the source repository and enables Wiki, create its
first page in GitHub; the Wiki repository can then be cloned. This follows
[GitHub's Wiki instructions](https://docs.github.com/en/communities/documenting-your-project-with-wikis/adding-or-editing-wiki-pages).

## Prepare locally

For the published project:

```sh
python3 scripts/export-wiki.py \
  --repository-url https://github.com/holiveiraa/moto-g4-linux
```

The command only writes `out/wiki/`. It rewrites mapped links to Wiki pages and
other source/assets links to the configured source repository/branch. It does
not call Git, log in, create anything remotely or publish.

## Publish or update, on the owner's instruction

After the first page exists, clone the `.wiki.git` URL supplied by GitHub, review
the generated Markdown, copy those files into that separate checkout and commit/
push there. Treat this as a separate publication action. Do not put `.private/`,
build artifacts or local development journals into either repository.

For subsequent updates, pull the Wiki's default branch first, regenerate from
the source revision being published, review the Markdown and push an ordinary
commit. Do not force-push or overwrite unrelated community pages. Source and
Wiki are separate histories; a successful source push does not update the Wiki.
For a fork, pass that fork's actual repository URL to the exporter.

For example, from the source checkout after its checks pass:

```sh
python3 scripts/export-wiki.py \
  --repository-url https://github.com/holiveiraa/moto-g4-linux
git clone https://github.com/holiveiraa/moto-g4-linux.wiki.git ../moto-g4-linux-wiki
git -C ../moto-g4-linux-wiki pull --ff-only
cp out/wiki/*.md ../moto-g4-linux-wiki/
git -C ../moto-g4-linux-wiki diff
```

Review the generated page list and the source revision before committing and
pushing the separate Wiki checkout. Its Home and sidebar should expose
**Hermes-Server-Agent**, **Hermes-Setup**, **Hermes-Quickstart-PT** and
**Screenshots**. Keep the existing **Hermes-Assistant-Plan** URL for research
links even though that page now documents the implementation too. The exporter
rewrites both Markdown images and HTML screenshot galleries to public asset URLs.

Maintain the guides in `docs/` (and the mapped credits/testing/license files),
then re-export. The Wiki is a view of the source docs, not a second installation
procedure. `wiki/pages.json` determines its published page set.
