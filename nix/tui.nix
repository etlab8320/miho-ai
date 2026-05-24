# nix/tui.nix — Miho TUI (Ink/React) compiled with tsc and bundled
{ pkgs, mihoNpmLib, ... }:
let
  src = ../ui-tui;
  npmDeps = pkgs.fetchNpmDeps {
    inherit src;
    hash = "sha256-F6/MzZOWc0zhW9mIfnaY+PrllPvJcsA/OdFdEM+NpLY=";
  };

  npm = mihoNpmLib.mkNpmPassthru { folder = "ui-tui"; attr = "tui"; pname = "miho-tui"; };

  packageJson = builtins.fromJSON (builtins.readFile (src + "/package.json"));
  version = packageJson.version;
in
pkgs.buildNpmPackage (npm // {
  pname = "miho-tui";
  inherit src npmDeps version;

  doCheck = false;
  npmFlags = [ "--legacy-peer-deps" ];

  installPhase = ''
    runHook preInstall

    mkdir -p $out/lib/miho-tui

    # Single self-contained bundle built by scripts/build.mjs (esbuild).
    cp -r dist $out/lib/miho-tui/dist

    # package.json kept for "type": "module" resolution on `node dist/entry.js`.
    cp package.json $out/lib/miho-tui/

    runHook postInstall
  '';
})
