import setuptools

with open("README.md","r",encoding="utf-8", errors="ignore") as fh:
	long_description = fh.read()

with open("requirements.txt","r",encoding="utf-8") as requirements:
	required = requirements.read().splitlines()

setuptools.setup(
	name="slip2sure",
	version="1.3.5",
	author="Slip2Sure Team",
	author_email="dev@slip2sure.com",
	description="A SDK for integrate Slip2Sure",
	long_description=long_description,
	long_description_content_type="text/markdown",
	url="https://github.com/Slip2Sure/slip2sure-py",
	keywords = ['api', 'slip2sure', 'slipverify','slipverification'],
	packages=setuptools.find_packages(),
	classifiers=[
		"Programming Language :: Python :: 3",
		"License :: OSI Approved :: MIT License",
		"Operating System :: OS Independent",
	],
	install_requires=required,
	python_requires=">=3.10",
	include_package_data=True
)