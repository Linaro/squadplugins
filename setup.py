from setuptools import setup

setup(
    name='squadplugins',
    version='1.0',
    author='Milosz Wasilewski',
    author_email='milosz.wasilewski@linaro.org',
    url='https://github.com/linaro/squadplugins',
    packages=['tradefed', 'ltp'],
    entry_points={
        'squad_plugins': [
            'tradefed=tradefed:Tradefed',
            'ltp=ltp:LtpLogs',
        ]
    },
    license='AGPLv3+',
    description="SQUAD plugini collection",
    long_description="""
    SQUAD pluginis that are compatible with Linaro's test-definitionis.
    The package contains plugin for parsing CTS/VTS results (tradefed)
    and LTP results (ltp).
    """,
    platforms='any',
    install_requires=['squad>=0.29', 'requests']
)
