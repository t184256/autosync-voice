{
  description = "Import, synchronize, merge and de-noise voice recordings that have been started almost simultaneously";

  inputs = {
    systems.url = "github:nix-systems/x86_64-linux";
    flake-utils.url = "github:numtide/flake-utils";
    flake-utils.inputs.systems.follows = "systems";
  };

  outputs = { self, nixpkgs, flake-utils, ... }@inputs:
    let
      deps = pyPackages: with pyPackages; [
        click click-default-group
        structlog
        dasbus
        ffmpeg-python
        numpy scipy
      ];
      tools = pkgs: pyPackages: (with pyPackages; [
        pytest pytestCheckHook
        mypy pytest-mypy
      ] ++ [pkgs.ruff]);

      autosync-voice-package = {pkgs, python3Packages}:
        python3Packages.buildPythonPackage {
          pname = "autosync-voice";
          version = "0.0.1";
          src = ./.;
          format = "pyproject";
          propagatedBuildInputs = deps python3Packages;
          nativeBuildInputs = [ python3Packages.setuptools ];
          checkInputs = tools pkgs python3Packages;
          postInstall = "mv $out/bin/autosync_voice $out/bin/autosync-voice";
        };

      overlay = final: prev: {
        pythonPackagesExtensions =
          prev.pythonPackagesExtensions ++ [(pyFinal: pyPrev: {
            autosync-voice = final.callPackage autosync-voice-package {
              python3Packages = pyFinal;
            };
          })];
      };

      overlay-all = nixpkgs.lib.composeManyExtensions [
        overlay
      ];
    in
      flake-utils.lib.eachDefaultSystem (system:
        let
          pkgs = import nixpkgs { inherit system; overlays = [ overlay-all ]; };
          defaultPython3Packages = pkgs.python311Packages;  # force 3.11

          deepfilternet-bin = pkgs.stdenv.mkDerivation {
            # maturin + git Cargo.lock deps = packaging problems
            pname = "deepfilternet-bin";
            version = "0.5.6";
            src = pkgs.fetchurl {
              url = "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/deep-filter-0.5.6-x86_64-unknown-linux-musl";
              sha256 = "sha256-cHdeJR7uRMDyRRoegzMmz4vLvjBNPnzRKFHm/Ocu99o=";
            };
            phases = [ "installPhase" ];
            installPhase = ''
              mkdir -p $out/bin
              install $src $out/bin/deepfilternet
            '';
          };

          autosync-voice = defaultPython3Packages.autosync-voice;
          app = flake-utils.lib.mkApp {
            drv = autosync-voice;
            exePath = "/bin/autosync-voice";
          };
        in
        {
          devShells.default = pkgs.mkShell {
            buildInputs = [(defaultPython3Packages.python.withPackages deps)];
            nativeBuildInputs = (tools pkgs defaultPython3Packages) ++ [
              deepfilternet-bin
            ];
            shellHook = ''
              export PYTHONASYNCIODEBUG=1 PYTHONWARNINGS=error
            '';
          };
          packages.autosync-voice = autosync-voice;
          packages.deepfilternet-bin = deepfilternet-bin;
          packages.default = autosync-voice;
          apps.autosync-voice = app;
          apps.default = app;
        }
    ) // { overlays.default = overlay; } // (
      let
        nixosModule = { config, lib, pkgs, ... }:
          let
            cfg = config.services.autosync-voice;
            pkg = self.packages.${pkgs.system}.autosync-voice;
          in {
            options.services.autosync-voice = {
              enable = lib.mkOption {
                description = "Enable autosync-voice service";
                type = lib.types.bool;
                default = false;
              };
              configFile = lib.mkOption {
                description = "Configuration file to use.";
                type = lib.types.str;
                default = "/etc/autosync-voice/config.toml";
              };
              user = lib.mkOption {
                description = "Service user to use";
                type = lib.types.str;
                default = "root";
              };
            };
            config = lib.mkIf cfg.enable {
              systemd.services.autosync-voice = {
                path = [ self.packages.${pkgs.system}.deepfilternet-bin ];
                description = "Automatic importer/aligner of voice recording";
                wantedBy = [ "multi-user.target" ];
                environment.AUTOSYNC_VOICE_CONFIG = cfg.configFile;
                serviceConfig = {
                  ExecStart = "${pkg}/bin/autosync-voice lurk";
                  Restart = "on-failure";
                  User = cfg.user;
                };
              };
            };
          };
        in
        {
          inherit nixosModule;
          nixosModules = {
            autosync-voice = nixosModule;
            default = nixosModule;
          };
        }
    );
}
