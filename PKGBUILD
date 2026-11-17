# Maintainer: Bill Sideris <bill88t@feline.gr>

pkgname=beryllium-sysconfig
pkgver=1.12.3
pkgrel=1
pkgdesc='Beryllium OS System Configurator and Management utility'
arch=(any)
url=https://github.com/BredOS/sys-config
license=('GPL3')

provides=("bredos-config" "beryllium-config" "beryl-config")
replaces=("bredos-sysconfig")
conflicts=("bredos-sysconfig")

depends=('python' 'dtc' 'python-beryllium-common>=1.11.0')
optdepends=('u-boot-update: Automatic U-Boot Updates')

source=('sys-config.py' 'beryllium-sysconfig.desktop')
sha256sums=('0b41435cf28a0c9758e7e345f57225e340b6eb50df99a4be2c664084d8c8f599'
            '29188c3e48d409370673bd31646673a3fb777fc2615b0477369a138efa568e3c')

package() {
    mkdir -p "${pkgdir}/usr/bin"
    install -Dm755 "${srcdir}/sys-config.py" "${pkgdir}/usr/bin/beryllium-config"
    ln -s "/usr/bin/beryllium-config" "${pkgdir}/usr/bin/bredos-config"
    ln -s "/usr/bin/beryllium-config" "${pkgdir}/usr/bin/beryl-config"
    install -Dm644 "${srcdir}/beryllium-sysconfig.desktop" "${pkgdir}/usr/share/applications/beryllium-sysconfig.desktop"
}
