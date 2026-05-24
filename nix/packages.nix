# nix/packages.nix — Miho Agent package built with uv2nix
{ inputs, ... }:
{
  perSystem =
    { pkgs, inputs', ... }:
    let
      mihoAgent = pkgs.callPackage ./miho-agent.nix {
        inherit (inputs) uv2nix pyproject-nix pyproject-build-systems;
        npm-lockfile-fix = inputs'.npm-lockfile-fix.packages.default;
        # Only embed clean revs — dirtyRev doesn't represent any upstream
        # commit, so comparing it would always claim "update available".
        rev = inputs.self.rev or null;
      };
    in
    {
      packages = {
        default = mihoAgent;
        tui = mihoAgent.mihoTui;
        web = mihoAgent.mihoWeb;

        fix-lockfiles = mihoAgent.mihoNpmLib.mkFixLockfiles {
          packages = [ mihoAgent.mihoTui mihoAgent.mihoWeb ];
        };
      };
    };
}
