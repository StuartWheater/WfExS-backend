#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright 2020-2021 Barcelona Supercomputing Center (BSC), Spain
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from __future__ import absolute_import

import os
import json
import subprocess
import tempfile

from typing import Dict, List, Tuple
from .common import *
from .container import ContainerFactory, ContainerFactoryException

DOCKER_PROTO = 'docker://'

class DockerContainerFactory(ContainerFactory):
    def __init__(self, cacheDir=None, local_config=None, engine_name='unset', tempDir=None):
        super().__init__(cacheDir=cacheDir, local_config=local_config, engine_name=engine_name, tempDir=tempDir)
        self.runtime_cmd = local_config.get('tools', {}).get('dockerCommand', DEFAULT_DOCKER_CMD)
    
    @classmethod
    def ContainerType(cls) -> ContainerType:
        return ContainerType.Docker
    
    def _inspect(self, dockerTag : ContainerTaggedName, matEnv) -> Tuple[int, bytes, str]:
        with tempfile.NamedTemporaryFile() as d_out, tempfile.NamedTemporaryFile() as d_err:
            self.logger.debug(f"querying docker container {dockerTag}")
            d_retval = subprocess.Popen(
                [self.runtime_cmd, 'inspect', dockerTag],
                env=matEnv,
                stdout=d_out,
                stderr=d_err
            ).wait()
            
            self.logger.debug(f"docker inspect {dockerTag} retval: {d_retval}")
            
            with open(d_out.name, mode="rb") as c_stF:
                d_out_v = c_stF.read().decode('utf-8', errors='continue')
            with open(d_err.name, mode="r") as c_stF:
                d_err_v = c_stF.read()
            
            self.logger.debug(f"docker inspect stdout: {d_out_v}")
            
            self.logger.debug(f"docker inspect stderr: {d_err_v}")
            
            return d_retval , d_out_v , d_err_v
    
    def _pull(self, dockerTag : ContainerTaggedName, matEnv) -> Tuple[int, str, str]:
        with tempfile.NamedTemporaryFile() as d_out, tempfile.NamedTemporaryFile() as d_err:
            self.logger.debug(f"pulling docker container {dockerTag}")
            d_retval = subprocess.Popen(
                [self.runtime_cmd, 'pull', dockerTag],
                env=matEnv,
                stdout=d_out,
                stderr=d_err
            ).wait()
            
            self.logger.debug(f"docker pull {dockerTag} retval: {d_retval}")
            
            with open(d_out.name, mode="r") as c_stF:
                d_out_v = c_stF.read()
            with open(d_err.name,"r") as c_stF:
                d_err_v = c_stF.read()
            
            self.logger.debug(f"docker pull stdout: {d_out_v}")
            
            self.logger.debug(f"docker pull stderr: {d_err_v}")
            
            return d_retval , d_out_v , d_err_v
    
    def materializeContainers(self, tagList: List[ContainerTaggedName], simpleFileNameMethod: ContainerFileNamingMethod, containers_dir: Union[RelPath, AbsPath] = None, offline: bool = False) -> List[Container]:
        """
        It is assured the containers are materialized
        """
        containersList = []
        
        matEnv = dict(os.environ)
        matEnv.update(self.environment)
        for tag in tagList:
            # It is an absolute URL, we are removing the docker://
            dockerTag = tag[len(DOCKER_PROTO):]  if tag.startswith(DOCKER_PROTO)  else tag
            
            self.logger.info(f"downloading docker container: {tag}")
            d_retval , d_out_v , d_err_v = self._inspect(dockerTag, matEnv)
            
            # Time to pull the image
            if d_retval != 0:
                d_retval , d_out_v , d_err_v = self._pull(dockerTag, matEnv)
                if d_retval == 0:
                    # Second try
                    d_retval , d_out_v , d_err_v = self._inspect(dockerTag, matEnv)
                    
            
            if d_retval != 0:
                errstr = """Could not materialize docker image {}. Retval {}
======
STDOUT
======
{}

======
STDERR
======
{}""".format(dockerTag, d_retval, d_out_v, d_err_v)
                raise ContainerFactoryException(errstr)
                
            # Parsing the output from docker inspect
            try:
                manifests = json.loads(d_out_v)
                manifest = manifests[0]
            except Exception as e:
                raise ContainerFactoryException(f"FATAL ERROR: Docker finished properly but it did not properly materialize {tag}: {e}")
            
            # Then, compute the signature
            tagId = manifest['Id']
            fingerprint = None
            if len(manifest['RepoDigests']) > 0:
                fingerprint = manifest['RepoDigests'][0]
            
            containersList.append(
                Container(
                    origTaggedName=tag,
                    taggedName=dockerTag,
                    signature=tagId,
                    fingerprint=fingerprint,
                    type=self.containerType
                )
            )
        
        return containersList
