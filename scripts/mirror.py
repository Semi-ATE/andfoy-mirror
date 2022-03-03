# -*- coding: utf-8 -*-
"""
Created on Thu Mar  3 07:34:27 2022

@author: hoeren
"""

import sys
import os
import requests
import json
import bz2
import subprocess
import shutil
import argparse

supported_subdirs = [
    'noarch',
    'linux-64', 
    'linux-aarch64', 
    'win-64', 
    'osx-64', 
    'osx-arm64',
]
packages_to_mirror = [
    'pyqt',
    'pyqtwebengine',
    'pyqtchart',
    'pyqt-impl',
    'pyqt5-sip',
    'qt-webengine',
]
source_channel = 'andfoy'
destination_channel = 'Semi-ATE'

class Mirror:

    def __init__(self, subdir, token):
        print(f"mirorring {subdir} packages :")
        source_packages = self.get_conda_packages_from(source_channel, subdir)
        mirrored_packages = self.get_conda_packages_from(destination_channel, subdir)
        for package in source_packages:
            if package not in mirrored_packages:
                self.mirror_package(subdir, package, token)
        print("Finished.")

    def get_conda_packages_from(self, channel, subdir):
        def get_repo_data(url):
            request = requests.get(url)
            if request.status_code == 200:
                data_json_bz2 = request.content
                data_json = bz2.decompress(data_json_bz2) 
                data = json.loads(data_json)["packages"]
            else:
                data = {}
            return data  
        
        all_packages = get_repo_data(f"https://conda.anaconda.org/{channel}/{subdir}/repodata.json.bz2")
        available_packages = []
        for package in all_packages:
            package_name = all_packages[package]['name']
            if package_name in packages_to_mirror:
                available_packages.append(package)
        return available_packages
        
    def download_package(self, channel, subdir, package):
        package_parts = package.split("-")
        package_version = package_parts[-2]
        package_name = "-".join(package_parts[0:-2])
        url = f"https://anaconda.org/{channel}/{package_name}/{package_version}/download/{subdir}/{package}"
        data = requests.get(url, allow_redirects=True)
        with open(package, 'wb') as fd:
            fd.write(data.content)
        return os.path.join(os.getcwd(), package)
    
    def upload_package(self, channel, path_to_package, token):
        retval = True
        cmd = ["anaconda", "-t", token, "upload", "-u", channel, path_to_package, "--force"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, output = p.communicate()
        output_lines = output.decode("utf-8").split("\n")  
    
        for output_line in output_lines:
            if "[ERROR]" in output_line:
                retval = False
        return retval
    
    def mirror_package(self, subdir, package, token):
        print(f"  {package} ... ", end="", flush=True)
        abs_package_file = self.download_package(source_channel, subdir, package)
        if self.upload_package(destination_channel, abs_package_file, token):
            print("Done.")
        else:
            print("Failed !!!")
        os.remove(abs_package_file)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('SUBDIR', type=str, default="noarch", help=f"The SUBDIR to work with. {supported_subdirs}")
    parser.add_argument('-t', type=str, help=f"anaconda.org token for the '{destination_channel}' channel.")
    args = parser.parse_args()
    
    if args.SUBDIR not in supported_subdirs:
        print(f"Error: '{args.SUBDIR}' is not supported, should be one of {supported_subdirs}")
        parser.print_help()
        sys.exit(1)
                
    mirror = Mirror(args.SUBDIR, args.t)
    
