{ pkgs }: {
  deps = [
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.jdk17_headless
    pkgs.curl
  ];
}
