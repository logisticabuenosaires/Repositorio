# coding: utf8
# intente algo como
@auth.requires_membership(role='Operador')
def index():
    if auth.user_id:
        if auth.has_membership (group_id=3):
            redirect(URL(r=request, c="cliente"))
        if auth.has_membership (group_id=4):
            redirect(URL(r=request, c="admin"))    
        return dict()
    response.flash = T('Bienvenido señor operador')
    return dict(message=T('Hola Operador'))
###########################################################################################################

@auth.requires_membership(role='Operador')
def user():
    return dict(form=auth())

############################################################################################################

@auth.requires_membership(role='Operador')
def download():
    return response.download(request,db)

############################################################################################################

@auth.requires_membership(role='Operador')
def call():
    session.forget()
    return service()
