# Plan: 3D tools, what to think about as 3D work grows

This plan surveys MCP servers, skills and tools that let Claude work in 3D: game engines, 3D
content apps (DCC), Adobe, and the browser 3D and asset pipeline. It ranks what Shivam should
decide first. Facts were read on 2026-11-01 from the linked pages. "Unverified" marks a fact no
source confirmed. Nothing was installed. Browser 3D design rules are not here: roadmap step
`web-design-guidelines` (browser design dos and don'ts) covers them.

Each tool in the three tables has a read-only vet note, per the decision on outside code: vet before any install.

## What to decide first, ranked

Each item names the outcome it serves.

1. **Pick the first 3D target.** Outcome: a cloud session can build and a reviewer can check the
   work. Browser 3D (three.js and glTF) is free and checks fully in a Linux container with no
   GPU. Godot is free, but its container check covers structure only; a rendered check is
   unverified. Unity and Unreal need the editor open on Shivam's computer, and Unity needs a licence
   even in batch mode. Page item 130.
2. **Code-running editor bridges.** Outcome: a bad tool call cannot harm Shivam's computer.
   Most engine and DCC servers run any code the model writes, on Shivam's computer, often over a
   local socket with no auth. Rule of thumb: prefer the vendor-official server; never
   auto-approve its code-run tool; turn off telemetry. Run it in a VM where the vendor says so
   (Blender Lab does).
3. **Where assets live.** Outcome: repos stay fast to clone and CI keeps working. GitHub blocks
   [files over 100 MiB](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github). Git LFS on a free or Pro plan gives [10 GiB storage and 10 GiB download](https://docs.github.com/en/billing/concepts/product-billing/git-lfs) a
   month, and stops for the month when used up with a $0 budget. Each CI checkout with LFS spends
   download quota. Page item 131.
4. **Asset licences.** Outcome: a site never ships a model file it may not redistribute. Poly
   Haven is [CC0](https://polyhaven.com/license) and safe. Fab (Epic) Standard licence: secondary sources quote it as barring
   redistribution of content "on a standalone basis", and the Reference-Only tier gives no source
   format ([Licenseware wiki](https://wiki.licenseware.io/wiki/fab-and-epic-content-licensing/),
   [Epic forum](https://forums.unrealengine.com/t/fab-com-free-assets-license-question/2337478/8)).
   Whether a raw .glb served to every browser, or put in a public repo, counts as standalone is
   unresolved: [fab.com/eula](https://www.fab.com/eula?lang=en) refuses cloud reads. Until a person
   reads it, use CC0 or self-made assets on sites and in public repos.
5. **Who buys licences.** Outcome: the right tier, no audit surprise. Unity Personal ends at
   $200K revenue plus funding; Unreal non-game seats ($1,850 a year, a 2024 figure) apply to companies above $1M annual revenue ([source](https://videogameschronicle.com/news/epic-confirms-its-new-unreal-engine-pricing-keeps-its-promise-not-to-change-it-for-game-developers)). The tier depends on which
   entity buys the licences. Page item 132.
6. **How a reviewer checks a scene.** Outcome: a scene is judged by a verdict, not by eye. All
   of this runs in a container with no GPU: `gltf-transform validate` or Khronos
   `gltf_validator` (non-zero exit on error); three.js `renderer.info` in a Playwright page for
   draw calls, triangles and textures; Playwright `toHaveScreenshot` on a SwiftShader render. A
   SwiftShader baseline will not match a GPU baseline, so pin the browser and OS. This becomes a
   lane once a target is picked, not a pick. Budgets: no published per-device budget was found
   (the Khronos table returned 404). Any triangle, draw-call or texture-memory budget is the
   owner's to set for a picked target; a reviewer measures it with these tools. It is not a
   builder rule.
7. **Hardware.** Outcome: no spend that buys nothing. No asset tool, validator or browser check
   needs a GPU. Editor work needs Shivam's desktop. A GPU matters only for heavy local renders.
8. **Start with the official connectors.** Outcome: fewer unvetted installs. Anthropic's
   directory lists Blender (Blender Lab), Adobe for creativity (hosted by Adobe, works from a
   cloud session) and Autodesk Fusion, all from 2026-04-28. The Blender connector's licence and container use are unverified.

Owner ruling, 2026-11-01 12:23 CST, keeps here: no optional standard becomes builder load. Item 6
adds only checks that catch a broken scene.

## Game engines

| Tool | What Claude can do | Maintainer, licence, last activity | Needs | Runs where | Vet note |
|---|---|---|---|---|---|
| [Unity MCP Server](https://docs.unity3d.com/Packages/com.unity.ai.assistant@2.17/manual/integration/unity-mcp-get-started.html) | Scenes, GameObjects, scripts, console, build settings | Unity (official), open beta, 2026-05; licence unverified | Unity 6+, editor open, Unity Cloud project, AI subscription | Shivam's computer | Beta; first connection needs a manual Allow |
| [CoplayDev/unity-mcp](https://github.com/CoplayDev/unity-mcp) | About 50 tools incl. tests, profiling, build | CoplayDev, MIT, v10.3.0 2026-10-04, 15.5k stars | Unity 2021.3–6, editor plugin, Python | Shivam's computer | Compiles C# it writes; remote HTTP auth unverified |
| [IvanMurzak/Unity-MCP](https://github.com/IvanMurzak/Unity-MCP) | Any C# via Roslyn, play mode, screenshots | individual, Apache-2.0, 2026-10-29 | Unity editor | Shivam's computer | Red flag: default setup routes through a third-party relay at ai-game.dev |
| [Unreal MCP plugin](https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor) | Actors, lighting, materials, automation tests | Epic (official), UE 5.8 Experimental; licence unverified, date unverified | UE 5.8 editor | Shivam's computer | HTTP on 127.0.0.1:8000 with no auth; analytics on by default |
| [Coding-Solo/godot-mcp](https://github.com/Coding-Solo/godot-mcp) | Run project, debug output, scenes, nodes | individual, MIT, last push 2026-04-16 | Godot binary, Node | Possibly a container (unverified) | No screenshot tool; `npx -y` unpinned |
| [tomyud1/godot-mcp](https://github.com/tomyud1/godot-mcp) | 69 tools incl. input and screenshots | individual, MIT, 2026-10-17 | editor plugin | Shivam's computer | Opens ports 6505 and 6510 |
| [Roblox Studio MCP](https://create.roblox.com/docs/en-us/studio/mcp) | Scripts, `execute_luau`, play mode, screen capture | Roblox (official), closed source; date unverified | Studio on Windows or Mac | Shivam's computer | Runs any Luau; inserted Store models can carry scripts |
| [PlayCanvas editor MCP](https://github.com/playcanvas/editor-mcp-server) | Entities, scripts, assets, builds, viewport capture | PlayCanvas (official), MIT, 2026-10-16 | Node 22, account, browser Editor tab | Shivam's computer | Can delete assets and branches in the PlayCanvas cloud |
| [bevy_brp](https://github.com/natepiano/bevy_brp) | Query and change the ECS, screenshots | individual, MIT/Apache-2.0, 2026-10-06 | Bevy app with RemotePlugin | Both | No auth on the BRP port |

Headless checks: Godot `--headless` gives structure checks but no image. Unity batch mode needs
a licence in the environment. Unreal `-nullrhi` gives structure checks; a render needs a GPU.
Roblox has no Linux build. The survey found no Claude skill from an engine vendor; the community pack
[awesome-gamedev-agent-skills](https://github.com/gamedev-skills/awesome-gamedev-agent-skills)
is not vetted.

## 3D content apps and Adobe

| Tool | What Claude can do | Maintainer, licence, last activity | Needs | Runs where | Vet note |
|---|---|---|---|---|---|
| [Blender connector](https://claude.com/connectors/blender) | 26 tools; 6 run in background Blender | Blender Lab (official), v1.0.3, launched 2026-04-28; licence unverified | Blender 5.1+, add-on | Shivam's computer; container use of the background tools unverified (needs Claude Desktop) | Its page says it runs model code "without any guards" and advises a VM |
| [ahujasid/blender-mcp](https://github.com/ahujasid/blender-mcp) | Any Python in Blender, asset import, AI model generation | individual, MIT, 2026-10-29, 33k stars | Blender, optional vendor API keys | Shivam's computer | Socket has no auth; telemetry on by default; safe mode off; a code-injection CVE is reported, unverified (NVD did not resolve it); repo name also listed as ahujasid/mcp-for-blender; prompts go to Tripo, Tencent, Rodin, Meshy |
| [Adobe for creativity](https://blog.adobe.com/en/publish/2026/04/28/adobe-for-creativity-connector) | 50+ tools across Photoshop, Illustrator, Express, Firefly and more | Adobe (official, hosted), GA 2026-04-28; licence unverified | Claude account; Adobe account optional | Hosted, works from a cloud session | Assets go to Adobe's cloud; does not drive desktop apps; Firefly text-to-image exposure unverified |
| [adb-mcp](https://github.com/mikechambers/adb-mcp) | Drives desktop Photoshop, Premiere, InDesign | individual, MIT, 2026-07-08 | Creative Cloud, UXP dev mode | Shivam's computer | Proof of concept, not endorsed by Adobe |
| [dcc-mcp Substance adapters](https://github.com/dcc-mcp) | Adapters exist | one person (unverified), MIT, 2026-10 | Painter or Designer running | Shivam's computer | No Adobe MCP for Substance. `execute_materialized_script` is "not a security sandbox" |
| [Cinema 4D built-in MCP](https://help.maxon.net) | Scene ops, `exec_python` | Maxon (official); licence unverified, date unverified | C4D licence | Shivam's computer (GUI only) | Python exec on by default; token sent unencrypted |
| [fxhoudinimcp](https://github.com/healkeiser/fxhoudinimcp) | 215 tools | individual, MIT, v2.28.3 2026-11-01 | Paid Houdini licence | Licensed container via hython | `execute_python` not sandboxed |
| [Rhino MCP Platform](https://github.com/mcneel/RhinoAI) | Script exec, viewport, Grasshopper | McNeel (official), MIT, 2026-10-30 | Rhino 9 WIP | Shivam's computer | Python exec |
| [Autodesk Fusion connector](https://claude.com/connectors/autodesk-fusion) | Geometry in the live session | Autodesk (official), launched 2026-04-28; licence unverified | Fusion subscription | Shivam's computer | Loopback only |
| [Meshy MCP](https://github.com/meshy-dev/meshy-mcp-server) | Text or image to 3D model | Meshy (official), MIT, 2026-10-30 | API key, Pro plan, credits | Container | Prompts and images go to Meshy |
| [Sketchfab MCP](https://github.com/gregkop/sketchfab-mcp-server) | Search and download models | individual, ISC; date unverified | API key | Container | Each model has its own licence |

The survey found no official server for Maya, 3ds Max, Houdini, Substance, Poly Haven or Sketchfab.
Hyper3D Rodin's server was archived on 2026-10-28. Maya and 3ds Max community servers are
Windows-leaning and stale or single-maintainer.

## Browser 3D and asset pipeline

All run in a Linux container with no GPU unless noted.

| Tool | What Claude can do | Maintainer, licence, last release | Vet note |
|---|---|---|---|
| [glTF-Transform CLI](https://gltf-transform.dev/cli) | inspect, validate, optimize, compress | Don McCurdy, MIT, 4.5.1 2026-09-28 | Native dependency (Sharp) |
| [gltfpack](https://github.com/zeux/meshoptimizer/blob/master/gltf/README.md) | Simplify and compress meshes | zeux, MIT, 1.3.0 2026-09-25 | KTX2 textures need the native binary |
| [Khronos glTF-Validator](https://github.com/KhronosGroup/glTF-Validator) | Spec check, non-zero exit on error | Khronos, Apache-2.0, last pre-release 2024-10 | Old but authoritative |
| [KTX-Software](https://github.com/KhronosGroup/KTX-Software/releases) | KTX2 and Basis textures | Khronos, v4.4.2 2025-10-04; licence unverified | Licence unverified |
| [OpenUSD usd-core](https://github.com/PixarAnimationStudios/OpenUSD/releases) | Read, write, check USD | Pixar, TOST-1.0, 26.11 2026-10-21 | Pixar's own licence; reaches local files only (unverified) |
| [screenshot-glb](https://github.com/Shopify/screenshot-glb) | GLB to image via headless Chrome | Shopify, MIT, 4.2.1 2026-09-17 | Downloads Chrome |
| [Playwright](https://playwright.dev/docs/api/class-snapshotassertions) + [pixelmatch](https://github.com/mapbox/pixelmatch) | WebGL page screenshots and diffs | Microsoft, Apache-2.0, 1.64.1 (date unverified); pixelmatch Mapbox, ISC, 8.0.0 (date unverified) | SwiftShader flag lowers browser sandbox security |
| [threejs-devtools-mcp](https://github.com/DmitriyGolub/threejs-devtools-mcp) | Inspect and change a live three.js scene | individual, MIT, 0.5.0 2026-10-14 | Opens Chrome remote control on port 9222; writes source files |
| [bpy](https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html) (Blender as Python module) | Scripted import, export, Cycles CPU render | Blender Foundation, GPL-3.0, 5.2.3; date unverified | EEVEE needs OpenGL |

## Also seen, not ranked or vetted

- [CoderGamester/mcp-unity](https://github.com/CoderGamester/mcp-unity): Unity, MIT, 2.0k stars.
- [chongdashu/unreal-mcp](https://github.com/chongdashu/unreal-mcp): Unreal, MIT, stale since 2025-04.
- [ChiR24/Unreal_mcp](https://github.com/ChiR24/Unreal_mcp): Unreal Remote Control API, MIT.
- [flopperam/unreal-engine-mcp](https://github.com/flopperam/unreal-engine-mcp): Unreal, no licence listed.
- [Natfii/UnrealClaude](https://github.com/Natfii/UnrealClaude): Claude Code inside UE 5.7.
- [ee0pdt/Godot-MCP](https://github.com/ee0pdt/Godot-MCP): Godot, stale since 2025-03.
- [o3de-mcp](https://pypi.org/project/o3de-mcp/): O3DE, 9 stars.
- [FunplayAI/funplay-cocos-mcp](https://github.com/FunplayAI/funplay-cocos-mcp): Cocos Creator, runs any JavaScript.
- [PatrickPalmer/MayaMCP](https://github.com/PatrickPalmer/MayaMCP): Maya, Windows, stale since 2025-05.
- [cl0nazepamm/3dsmax-mcp](https://github.com/cl0nazepamm/3dsmax-mcp): 3ds Max, Windows, runs MAXScript.
- [ttiimmaacc/cinema4d-mcp](https://github.com/ttiimmaacc/cinema4d-mcp): Cinema 4D, runs Python.
- [jingcheng-chen/rhinomcp](https://github.com/jingcheng-chen/rhinomcp): Rhino 8, Python and C# exec can be turned off.
- [y1uda Painter MCP Pro](https://y1uda.itch.io/painter-mcp-pro): Substance Painter, $15, closed.
- [Tripo-Developer/tripo-mcp](https://github.com/Tripo-Developer/tripo-mcp): stale alpha.
- [DeemosTech/rodin-api-mcp](https://github.com/DeemosTech/rodin-api-mcp): archived 2026-10-28.
- [RN0000/polyhaven-mcp](https://github.com/RN0000/polyhaven-mcp): Poly Haven, not vetted.
- [daslabhq/openusd-mcp](https://github.com/daslabhq/openusd-mcp): USD inspect, 0.1.0.
- [deya-0x/ThreeJSMCP](https://github.com/deya-0x/ThreeJSMCP): three.js docs search.
- [babylonjs-mcp](https://lobehub.com/mcp/thaneplummer-babylonjs-mcp): Babylon.js docs, unverified.
- [pmndrs/gltfjsx](https://github.com/pmndrs/gltfjsx): GLB to React component, no release since 2024-11.
- [draco3d](https://github.com/google/draco): Google mesh compression, Apache-2.0.
- [model-viewer](https://github.com/google/model-viewer): Google web viewer, Apache-2.0.
- Skill packs, not vetted: [awesome-gamedev-agent-skills](https://github.com/gamedev-skills/awesome-gamedev-agent-skills), [OpenAEC Three.js pack](https://github.com/OpenAEC-Foundation/Three.js-Claude-Skill-Package), [meshy-3d-agent](https://github.com/meshy-dev/meshy-3d-agent).

## Costs, read 2026-11-01

- Unity Pro: $2,310 per seat per year. Personal free up to $200K revenue plus funding.
  ([source](https://unity.com/products/pricing-updates))
- Unreal: games free to $1M gross, then 5%. Non-game seat $1,850 a year, a 2024 figure, for companies above $1M annual revenue; current
  price unverified.
  ([source](https://videogameschronicle.com/news/epic-confirms-its-new-unreal-engine-pricing-keeps-its-promise-not-to-change-it-for-game-developers))
- Adobe Substance 3D Collection: $59.99 a month for individuals, $119.99 for teams,
  unverified. ([source](https://helpx.adobe.com/no/substance-3d/pricing-change.html))
- Git LFS over quota: $0.07 per GiB-month storage, $0.0875 per GiB download.
  ([source](https://docs.github.com/en/billing/concepts/product-billing/git-lfs))
- Texture memory: one 4096×4096 RGBA texture uses about 85 MiB on the GPU with mipmaps; a PBR
  material often has 3 to 5 maps.

## Open checks

- A session on Shivam's computer reads the Fab EULA on raw-file redistribution, and Epic's
  current seat price. Both pages refuse cloud reads.
- Confirm the Blender Lab connector's licence (page returned 403).
- Confirm whether the Adobe connector exposes Firefly text-to-image.
