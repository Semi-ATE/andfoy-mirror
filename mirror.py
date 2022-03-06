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
import yaml
import shutil

class Mirror:

    subdirs = [
        'noarch',
        'linux-64', 
        'linux-aarch64', 
        'win-64', 
        'osx-64', 
        'osx-arm64',
    ]    

    def __init__(self, verbose=True):
        self.verbose = verbose
        self.my_fpath = os.path.abspath(os.path.normpath(__file__))
        self.repo_root = os.path.dirname(self.my_fpath)
        self.my_name = os.path.basename(self.my_fpath).replace(".py", "")

        # read the mirror configuration file
        self.config_fpath = os.path.join(self.repo_root, f"{self.my_name}.yaml")
        if not os.path.exists(self.config_fpath):
            raise f"Can not find '{self.config_fpath}'"
        with open(self.config_fpath) as fd:
            self.config = yaml.load(fd, Loader=yaml.FullLoader)
        
        # post-process for minimal keys
        key_problem = False
        for entry in self.config['mirror']:
            if 'packages' not in entry:
                key_problem = True
                print(f"ERROR: 'packages' key not found in {entry}")
            if 'token' not in entry:
                key_problem = True
                print(f"ERROR: 'token' key not found in {entry}")
            if 'source' not in entry:
                key_problem = True
                print(f"ERROR: 'source' key not found in {entry}")
            if 'destination' not in entry:
                key_problem = True
                print(f"ERROR: 'destination' key not found in {entry}")
        if key_problem:
            sys.exit(1)
        
        print("preparing to mirror packages ", end="", flush=True)
        
        # post-process for packages
        for entry in self.config['mirror']:
            if isinstance(entry['packages'], str):
                entry['packages'] = [entry['packages']]
        print(".", end="", flush=True)      
        
        # prepare the download folder
        self.download_folder = os.path.join(self.repo_root, 'download')
        if os.path.isdir(self.download_folder):
            for filename in os.listdir(self.download_folder):
                file_path = os.path.join(self.download_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                except Exception as e:
                    print('Failed to delete %s. Reason: %s' % (file_path, e))
                    sys.exit(1)
        else:
            os.makedirs(self.download_folder, exist_ok=True)
        print(".", end="", flush=True)

        # post-process for subdirs
        subdir_problem = False
        for entry in self.config['mirror']:
            if not 'subdirs' in entry:
                entry['subdirs'] = self.subdirs
            else:
                for subdir in entry['subdirs']:
                    if subdir not in self.subdirs:
                        subdir_problem = True
                        print(f"ERROR: subdir '{subdir}' not supported.")
        if subdir_problem:
            sys.exit(1)
        print(".", end="", flush=True)
            
        # post-process for token
        token_problem = False
        for entry in self.config['mirror']:
            destination = entry['destination']
            raw_token = entry['token']
            if raw_token.strip().startswith("${{") and raw_token.strip().endswith("}}"):
                env_token = raw_token.replace("${{","").replace("}}", "").strip()
                if env_token in os.environ:
                    entry['token'] = os.environ[env_token]
                else:
                    token_problem = True
                    print(f"ERROR: token for the '{destination}' channel is not defined.")
        if token_problem:
            sys.exit(1)
        print(".", end="", flush=True)

        # post-process for source channel
        source_problems = []
        for entry in self.config['mirror']:
            source = entry['source']
            if not self.channel_exists(source):
                source_problems.append(f"ERROR: source channel '{source}' does not exist.")
        if source_problems:
            print()
            for source_problem in source_problems:
                print(source_problem)
            sys.exit(1)
        else:
            print(".", end="", flush=True)
        
        # post-process for destination channel
        destination_problems = []
        for entry in self.config['mirror']:
            destination = entry['destination']
            if not self.channel_exists(destination):
                destination_problems.append(f"ERROR: destination channel '{destination}' does not exist.")
        if destination_problems:
            print()
            for destination_problem in destination_problems:
                print(destination_problem)
            sys.exit(1)
        else:
            print(". Done.")

        # do the mirroring
        print("mirroring packages : ")
        for entry in self.config['mirror']:
            source = entry['source']
            destination = entry['destination']
            packages = entry['packages']
            subdirs = entry['subdirs']
            token = entry['token']
            for package in packages:
                self.mirror_package(package, source, subdirs, destination, token)
        print("Finished.")

    def channel_exists(self, channel):
        url = f"https://conda.anaconda.org/{channel}/"
        r = requests.get(url)
        if r.status_code != 200:
            return False
        return True
    
    def get_packages(self, channel, package_name=""):
        retval = []
        for subdir in self.subdirs:
            url = f"https://conda.anaconda.org/{channel}/{subdir}/repodata.json.bz2"
            r = requests.get(url)
            packages_json_bz2 = r.content
            packages_json = bz2.decompress(packages_json_bz2) 
            packages = json.loads(packages_json)["packages"]
            if package_name:
                for package in packages:
                    if packages[package]['name'] == package_name:
                        retval.append(f"{channel}/{subdir}/{package}")
            else:
                for package in packages:
                    retval.append(f"{channel}/{subdir}/{package}")
        return retval
    
    def package_exists(self, channel, package_name):
        if not self.channel_exists(channel):
            return False
        retval = self.get_packages(channel, package_name)
        return not retval == []

    def mirror_package(self, package_name, source, subdirs, destination, token):
        print(f"  {source}/{package_name} -> {destination}/{package_name} ", end="", flush=True)

        source_packages = self.get_packages(source, package_name)
        bare_source_packages = []
        for source_package in source_packages:
            bare_source_packages.append(source_package.split("/")[-1])
        print(".", end="", flush=True)    
            
        destination_packages = self.get_packages(destination, package_name)
        bare_destination_packages = []
        for destination_package in destination_packages:
            bare_destination_packages.append(destination_package.split("/")[-1])
        print(".", end="", flush=True)    
            
        packages_to_mirror = []
        for bare_source_package in bare_source_packages:
            if bare_source_package not in bare_destination_packages:
                packages_to_mirror.append(bare_source_package)
        packages_to_mirror = len(packages_to_mirror)
        print(".", end="", flush=True)    
        
        if packages_to_mirror == 0:
            print(" Nothing to be done.")
        else:
            print(f" ({packages_to_mirror} packages) ", end="", flush=True)
            for source_package in source_packages:
                channel, subdir, package = source_package.split("/")
                package_fpath = self.download_package(channel, subdir, package)
                print("🠗", end="", flush=True)
                self.upload_package(destination, package_fpath, token)
                print("🠕", end="", flush=True)
            print(" Done.")

        
    def download_package(self, channel, subdir, package):
        package_parts = package.split("-")
        package_version = package_parts[-2]
        package_name = "-".join(package_parts[0:-2])
        url = f"https://anaconda.org/{channel}/{package_name}/{package_version}/download/{subdir}/{package}"
        package_path = os.path.join(self.download_folder, channel, package_name, subdir)
        if not os.path.exists(package_path):
            os.makedirs(package_path)
        package_fpath = os.path.join(package_path, package) 
        if not os.path.exists(package_fpath):
            r = requests.get(url, allow_redirects=True)
            if r.status_code == 200:
                with open(package_fpath, 'wb') as fd:
                    fd.write(r.content)
        return package_fpath
    
    def upload_package(self, channel, package_fpath, token):
        retval = True
        cmd = ["anaconda", "-t", token, "upload", "-u", channel, package_fpath, "--force"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _, output = p.communicate()
        output_lines = output.decode("utf-8").split("\n")  
    
        for output_line in output_lines:
            if "[ERROR]" in output_line:
                retval = False
        return retval

if __name__ == '__main__':
    os.environ['SEMI_ATE_UPLOAD_TOKEN'] = "Se-0c36792b-1b02-4bfa-8d3d-10e2ecea1df7"
    os.environ['NEROHMOT_UPLAOAD_TOKEN'] = "ne-6e4be89f-1db2-4e0e-8289-8082cc0eb63b"
    mirror = Mirror()

