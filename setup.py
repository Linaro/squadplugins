from setuptools import setup

setup(
    name='squad-linaro-plugins',
    version='1.33.1',
    author='Charles Oliveira',
    author_email='charles.oliveira@linaro.org',
    url='https://github.com/linaro/squadplugins',
    packages=['tradefed', 'ltp', 'mmtests'],
    entry_points={
        'squad_plugins': [
            'tradefed=tradefed:Tradefed',
            'ltp=ltp:LtpLogs',
            'mmtests=mmtests:Mmtests',
        ]
    },
    license='AGPLv3+',
    description="SQUAD plugins collection",
    long_description="""
    SQUAD plugins that are compatible with Linaro's test-definitions.
    The package contains plugin for parsing CTS/VTS results (tradefed)
    and LTP results (ltp).
    """,
    platforms='any',
    install_requires=['squad[postgres]>=1.81', 'requests']
)
