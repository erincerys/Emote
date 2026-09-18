# Maintainer: erin
# Builds the erincerys fork of Emote from the local git checkout (master).

pkgname=emote-git
pkgver=4.1.0.r20.g2d045a2
pkgrel=1
pkgdesc='Modern popup emoji picker (erincerys fork)'
arch=('any')
url='https://github.com/erincerys/Emote'
license=('GPL-3.0-only')
depends=('python' 'gtk3' 'python-gobject' 'libkeybinder3' 'python-setproctitle'
         'dbus-python' 'hicolor-icon-theme' 'emoji-font')
makedepends=('git' 'meson' 'ninja')
optdepends=('xdotool: automatic pasting in X11'
            'wl-clipboard: automatic copying in Wayland')
provides=('emote')
conflicts=('emote')
_repo=/media/hdd-array/tech/dev/repos/github/erincerys/Emote
source=("emote::git+file://${_repo}#branch=master")
sha256sums=('SKIP')

pkgver() {
  cd emote
  git describe --long --tags | sed 's/^v//; s/\([^-]*-g\)/r\1/; s/-/./g'
}

build() {
  # pyenv shims sit first on PATH; keep them out of the launcher shebang
  export PATH=$(printf '%s' "$PATH" | tr ':' '\n' | grep -v '\.pyenv' | paste -sd:)
  arch-meson emote build
  meson compile -C build
}

package() {
  meson install -C build --destdir "$pkgdir"
  install -Dm644 emote/LICENSE.md "$pkgdir/usr/share/licenses/$pkgname/LICENSE.md"

  local desktop="$pkgdir/usr/share/applications/com.tomjwatson.Emote.desktop"
  sed -i '/^X-Flatpak=/d' "$desktop"
  install -Dm644 "$desktop" "$pkgdir/etc/xdg/autostart/com.tomjwatson.Emote.desktop"

  /bin/rm -rf "$pkgdir"/usr/share/emote/emote/{__pycache__,emote.in,meson.build}
  /bin/rm -f "$pkgdir"/usr/share/emote/static/meson.build
}
