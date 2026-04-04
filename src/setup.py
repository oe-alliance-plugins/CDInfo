from setuptools import setup
import setup_translate

pkg = 'Extensions.CDInfo'
setup(name='enigma2-plugin-extensions-cdinfo',
       version='3.0',
       description='read audio CD-Text or query CDDB for album and track info',
       package_dir={pkg: 'CDInfo'},
       packages=[pkg],
       package_data={pkg: ['images/*.png', '*.png', '*.xml', 'locale/*/LC_MESSAGES/*.mo', 'plugin.png', 'maintainer.info']},
       cmdclass=setup_translate.cmdclass,  # for translation
      )
