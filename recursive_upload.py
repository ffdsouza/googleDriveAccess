#!/usr/local/bin/python
# -*- coding: utf-8 -*-
'''recursive_upload
This program creates so many directories and files to remote Google Drive.
But you should upload them into an archive (.tar.gz).
'''

import sys, os
import sqlite3
import socket
import pprint

from apiclient.http import MediaFileUpload
from oauth2client.anyjson import simplejson
import googleDriveAccess

import logging
logging.basicConfig()

FOLDER_TYPE = 'application/vnd.google-apps.folder'
MAX_CID_LEN = 256
MAX_KEY_LEN = 256
MAX_PATH_LEN = 1024
CACHE_FOLDERIDS = 'cache_folderIds.sl3'
BACKUP = 'recursive_upload_backup'

def prepare_folder(da, folderIds, folder):
  q = folder.replace('\\', '/')
  if len(q) > MAX_PATH_LEN:
    raise Exception('folder length is too long > %s' % MAX_PATH_LEN)
  if q[0] != '/':
    raise Exception('folder does not start with / [%s]' % folder)
  if q[-1] == '/' or not len(q): # root or endswith '/'
    return ('root', '/')
  cn = sqlite3.connect(folderIds)
  cn.row_factory = sqlite3.Row
  cur = cn.cursor()
  cur.execute('''select key, val from folderIds where val='%s';''' % q)
  row = cur.fetchone()
  cur.close()
  cn.close()
  if row is None:
    parent, p = os.path.split(q)
    parentId, r = prepare_folder(da, folderIds, parent)
    query = "'%s' in parents and title='%s' and mimeType='%s' %s" % (
      parentId, p, FOLDER_TYPE, 'and explicitlyTrashed=False')
    entries = da.execQuery(query, True, True, **{'maxResults': 2})
    if not len(entries['items']):
      folderId, folderObj = da.createFolder(p, parentId)
    else:
      folderId = entries['items'][0][2]
      if len(entries['items']) > 1: sys.stderr.write('duplicated [%s]\a\n' % q)
    cn = sqlite3.connect(folderIds)
    cn.execute('''insert into folderIds (key, val) values ('%s', '%s');''' % (
      folderId, q))
    cn.commit()
    cn.close()
  else:
    folderId = row['key']
  return (folderId, q)

def uploadFile(da, path, filename, parentId):
  #body = {'title': filename, 'mimeType': mimetype, 'description': description}
  body = {'title': filename, 'description': filename}
  body['parents'] = [{'id': parentId}]
  filepath = os.path.join(path, filename)
  #mbody = MediaFileUpload(filepath, mimetype=mimetype, resumable=True)
  mbody = MediaFileUpload(filepath, resumable=True)
  fileObj = da.drive_service.files().insert(body=body, media_body=mbody).execute()
  return (fileObj['id'], fileObj)

def recursive_upload(da, basedir, backup, folderIds):
  b = os.path.join(basedir, backup)
  backup_id, q = prepare_folder(da, folderIds, b[len(basedir):]) # set [0]='/'
  for path, dirs, files in os.walk(b):
    p_id, q = prepare_folder(da, folderIds, path[len(basedir):]) # set [0]='/'
    for d in dirs:
      print 'D %s %s' % (q, d) # os.path.join(path, d)
    for f in files:
      print 'F %s %s' % (q, f) # os.path.join(path, f)
      fileId, fileObj = uploadFile(da, path, f, p_id)
      # pprint.pprint((fileId, fileObj))

def main(basedir):
  folderIds = os.path.join(basedir, CACHE_FOLDERIDS)
  if not os.path.exists(folderIds):
    cn = sqlite3.connect(folderIds)
    cn.execute('''create table clientIds (
cli integer primary key autoincrement,
client_id varchar(%d) unique not null);''' % (
      MAX_CID_LEN))
    cn.execute('''create unique index clientIds_idx_client_id
on clientIds (client_id);''')
    cn.execute('''create table folderIds (
key varchar(%d) primary key not null,
val varchar(%d) unique not null,
cli integer default 1,
fol integer default 1,
flg integer default 0);''' % (
      MAX_KEY_LEN, MAX_PATH_LEN))
    cn.execute('''create unique index folderIds_idx_val
on folderIds (val);''')
    cn.execute('''create index folderIds_idx_cli
on folderIds (cli);''')
    cn.execute('''insert into folderIds (key, val) values ('root', '/');''')
    cn.commit()
    cn.close()
  da = googleDriveAccess.DAClient(basedir)
  recursive_upload(da, basedir, BACKUP, folderIds)
  # test for bottomup directory creation
  for subfolder in ['sub1/sub2', 'sub1/sub3', 'sub4']:
    p_id, q = prepare_folder(da, folderIds, '/%s/testbottomup/%s' % (
      BACKUP, subfolder))

if __name__ == '__main__':
  logging.getLogger().setLevel(getattr(logging, 'INFO')) # ERROR
  try:
    main(os.path.dirname(__file__))
  except (socket.gaierror, ), e:
    sys.stderr.write('socket.gaierror')
