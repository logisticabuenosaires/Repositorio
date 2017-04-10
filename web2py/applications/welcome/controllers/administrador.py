@auth.requires_membership(role='Administrador')
def index():
    if auth.user_id:
        if auth.has_membership (group_id=3):
            redirect(URL(r=request, c="cliente"))
        if auth.has_membership (group_id=5):
            redirect(URL(r=request, c="Operador"))    
        return dict()
    return dict()
############################################################################################################

@auth.requires_membership(role='Administrador')    
def user():
    return dict(form=auth())
