# Maintainer: Bill Sideris <bill88t@feline.gr>

pkgname=beryllium-sysconfig
pkgver=1.11.0
pkgrel=1
pkgdesc='BredOS System Configurator and Management utility'
arch=(any)
url=https://github.com/BredOS/sys-config
license=('GPL3')

provides=("bredos-config" "beryllium-config" "beryl-config")
replaces=("bredos-sysconfig")
conflicts=("bredos-sysconfig")

depends=('python' 'dtc' 'python-beryllium-common>=1.11.0')
optdepends=('u-boot-update: Automatic U-Boot Updates')

source=('sys-config.py' 'beryllium-sysconfig.desktop')
sha256sums=('c01054ad9fd0f0c7dc55ee1bb21f747ee4cad0e8902854f487ee7eff6fb85abb'
            '29188c3e48d409370673bd31646673a3fb777fc2615b0477369a138efa568e3c')

package() {
    mkdir -p "${pkgdir}/usr/bin"
    install -Dm755 "${srcdir}/sys-config.py" "${pkgdir}/usr/bin/beryllium-config"
    ln -s "/usr/bin/beryllium-config" "${pkgdir}/usr/bin/bredos-config"
    ln -s "/usr/bin/beryllium-config" "${pkgdir}/usr/bin/beryl-config"
    install -Dm644 "${srcdir}/beryllium-sysconfig.desktop" "${pkgdir}/usr/share/applications/beryllium-sysconfig.desktop"
}
