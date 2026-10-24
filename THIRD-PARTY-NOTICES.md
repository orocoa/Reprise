# Third-party notices

Reprise source code is distributed under the MIT license in `LICENSE`.
Bundled third-party assets retain their original licenses and notices:

| Asset | License | Bundled notice |
| --- | --- | --- |
| Inter Variable | SIL Open Font License 1.1 | `web/fonts/Inter-OFL.txt` |
| Kode Mono | SIL Open Font License 1.1 | `web/fonts/KodeMono-OFL.txt` |
| Departure Mono 1.500 | SIL Open Font License 1.1 | `web/fonts/DepartureMono-OFL.txt` |
| 正格点黑 (ZhengGeDianHei) | SIL Open Font License 1.1 | `web/fonts/ZhengGeDianHei-OFL.txt` |
| Feather edit-2 icon and derived inline path | MIT | `web/icons/feather-LICENSE` |
| Tabler pencil icon | MIT | `web/icons/tabler-LICENSE` |

For source/Python-package installations, Playwright is an optional dependency
installed separately, and Git, Python, Node and browsers come from the user's
environment. The standalone macOS runtime package instead includes pinned
copies of Python, Git, Node, Playwright Core and Chromium Headless Shell.

In the standalone package, the asset paths above are prefixed with
`app/reprise/` (for example `app/reprise/web/fonts/Inter-OFL.txt`). Runtime
versions, upstream URLs and archive hashes are recorded in
`runtime/upstream-lock.json`. Additional Python and Git licenses are under
`licenses/`; Node's license remains in `runtime/node/LICENSE`, Playwright Core's
LICENSE/NOTICE/ThirdPartyNotices.txt remain in `runtime/node_modules/playwright-core/`,
and the browser notice remains beside its binary as `LICENSE.headless_shell`.
Git and dugite-native source/build archives are included under `sources/`.
These components retain their respective licenses; Reprise's MIT license does
not replace them. The compact screenshot package does not include FFmpeg or
support video recording.

Imported repositories and screenshots/videos provided by users keep their
original ownership and licenses. Reprise's license does not relicense them.
