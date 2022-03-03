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
import argparse
import yaml

# supported_subdirs = [
#     'noarch',
#     'linux-64', 
#     'linux-aarch64', 
#     'win-64', 
#     'osx-64', 
#     'osx-arm64',
# ]
# packages_to_mirror = [
#     'pyqt',
#     'pyqtwebengine',
#     'pyqtchart',
#     'pyqt-impl',
#     'pyqt5-sip',
#     'qt-webengine',
# ]
# source_channel = 'andfoy'
# destination_channel = 'Semi-ATE'

class Mirror:

    def __init__(self, subdir, token):
        self.repo_root = os.path.dirname(os.path.normpath(__file__))

        self.download_folder = os.path.join(self.repo_root, 'download')
        os.makedirs(self.download_folder, exist_ok=True)

        self.setup_fpath = os.path.join(self.repo_root, "mirror.yaml")
        with open(self.setup_fpath) as fd:
            self.setup = yaml.load(fd, Loader=yaml.FullLoader)
        
        if subdir not in self.setup['subdirs']:
            raise KeyError
        
        print(f"mirorring {subdir} packages :")
        source_packages = self.get_conda_packages_from(self.setup['source_channel'], subdir)
        mirrored_packages = self.get_conda_packages_from(self.setup['destination_channel'], subdir)
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
            if package_name in self.setup['packages_to_mirror']:
                available_packages.append(package)
        return available_packages
        
    def download_package(self, channel, subdir, package):
        package_parts = package.split("-")
        package_version = package_parts[-2]
        package_name = "-".join(package_parts[0:-2])
        url = f"https://anaconda.org/{channel}/{package_name}/{package_version}/download/{subdir}/{package}"
        data = requests.get(url, allow_redirects=True)
        package_fpath = os.path.join(self.download_folder, package) 
        with open(package_fpath, 'wb') as fd:
            fd.write(data.content)
        return package_fpath
    
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
        abs_package_file = self.download_package(self.setup['source_channel'], subdir, package)
        if self.upload_package(self.setup['destination_channel'], abs_package_file, token):
            print("Done.")
        else:
            print("Failed !!!")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('SUBDIR', type=str, default="noarch", help="The SUBDIR to work with.")
    parser.add_argument('-t', type=str, help="anaconda.org token for the destination channel.")
    args = parser.parse_args()
                    
    mirror = Mirror(args.SUBDIR, args.t)
    
