# GitHub Wiki

The repository documentation works immediately through ordinary GitHub links.
The optional Wiki presents the same material as a browsable handbook, with Home,
sidebar, hardware matrix, agent installation, builds, usage and troubleshooting.

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

Maintain the guides in `docs/` (and the mapped credits/testing/license files),
then re-export. The Wiki is a view of the source docs, not a second installation
procedure. `wiki/pages.json` determines its published page set.
