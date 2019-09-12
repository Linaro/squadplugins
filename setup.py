from setuptools import setup

setup(
    name='squad-linaro-plugins',
    version='1.10',
    author='Milosz Wasilewski',
    author_email='milosz.wasilewski@linaro.org',
    url='https://github.com/linaro/squadplugins',
    packages=['tradefed', 'ltp', 'kernel_issues'],
    entry_points={
        'squad_plugins': [
            'tradefed=tradefed:Tradefed',
            'ltp=ltp:LtpLogs',
            'kernel_issues=kernel_issues:KernelIssues',
        ]
    },
    license='AGPLv3+',
    description="SQUAD plugins collection",
    long_description="""
    SQUAD plugins that are compatible with Linaro's test-definitions.
    The package contains plugin for parsing CTS/VTS results (tradefed),
    LTP results (ltp) and a custom Kernel log parser.
    """,
    platforms='any',
    install_requires=['squad>=0.29', 'requests']
)
