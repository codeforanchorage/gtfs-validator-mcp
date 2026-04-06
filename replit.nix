{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.jdk17_headless
    pkgs.curl
    pkgs.rustc
    pkgs.cargo
    pkgs.gcc
    pkgs.openssl
    pkgs.pkg-config
  ];
}
