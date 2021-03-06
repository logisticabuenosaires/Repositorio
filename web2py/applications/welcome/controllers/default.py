# -*- coding: utf-8 -*-
# this file is released under public domain and you can use without limitations

#########################################################################
## This is a samples controller
## - index is the default action of any application
## - user is required for authentication and authorization
## - download is for downloading files uploaded in the db (does streaming)
## - call exposes all registered services (none by default)
#########################################################################

def index():
    if auth.user_id:
        if auth.has_membership (group_id=3):
            redirect(URL(r=request, c="cliente"))
        if auth.has_membership (group_id=4):
            redirect(URL(r=request, c="Administrador"))
        if auth.has_membership (group_id=5):
            redirect(URL(r=request, c="Operador"))    
        return dict()
    response.flash = "Bienvenido a su gestor!"
    return dict(message=T('Bienvenido a su gestor'))

def user():
    if auth.user_id:
        if auth.has_membership (group_id=3):
            redirect(URL(r=request,c='cliente',f='user/not_authorized'))
        if auth.has_membership (group_id=4):
            redirect(URL(r=request,c='Administrador',f='user/not_authorized'))
        if auth.has_membership (group_id=5):
            redirect(URL(r=request, c="Operador",f='user/not_authorized'))      
        return dict()
    return dict(form=auth())


def download():
    """
    allows downloading of uploaded files
    http://..../[app]/default/download/[filename]
    """
    return response.download(request,db)


def call():
    """
    exposes services. for example:
    http://..../[app]/default/call/jsonrpc
    decorate with @services.jsonrpc the functions to expose
    supports xml, json, xmlrpc, jsonrpc, amfrpc, rss, csv
    """
    return service()


@auth.requires_signature()
def data():
    """
    http://..../[app]/default/data/tables
    http://..../[app]/default/data/create/[table]
    http://..../[app]/default/data/read/[table]/[id]
    http://..../[app]/default/data/update/[table]/[id]
    http://..../[app]/default/data/delete/[table]/[id]
    http://..../[app]/default/data/select/[table]
    http://..../[app]/default/data/search/[table]
    but URLs must be signed, i.e. linked with
      A('table',_href=URL('data/tables',user_signature=True))
    or with the signed load operator
      LOAD('default','data.load',args='tables',ajax=True,user_signature=True)
    """
    return dict(form=crud())
def fast_download():
   import os, time
   # very basic security (only allow fast_download on your_table.upload_field):
   if not request.args(0).startswith("articulo.imagen"):
       return download()
   # remove/add headers that prevent/favors client-side caching
   del response.headers['Cache-Control']
   del response.headers['Pragma']
   del response.headers['Expires']
   filename = os.path.join(request.folder,'uploads',request.args(0))
   # send last modified date/time so client browser can enable client-side caching
   response.headers['Last-Modified'] = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.localtime(os.path.getmtime(filename)))
   return response.stream(open(filename,'rb'))
def aboutme():

    response.flash = "CONOZCANOS!"
    return dict(message=T('Hello World'))
