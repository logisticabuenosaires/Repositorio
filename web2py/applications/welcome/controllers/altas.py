# coding: utf8
# try something like
def index():
    return dict()
def articulos():
    form=SQLFORM(db.articulo)
    if form.accepts(request.vars, session):
        response.flash = "Registro agregado!"
    elif form.errors:
        response.flash = "Errores!"
    else:
        response.flash = "Completar!" 

    return dict( f=form)
######################################


##################################
def Altas_chofer():
    form=SQLFORM(db.chofer, submit_button='Grabar')
    if form.accepts(request.vars, session):
        response.flash = "Registro agregado!"
    elif form.errors:
        response.flash = "Errores!"
    else:
        response.flash = "Completar!" 

    return dict( f=form)



###################################
  
###############################################
def alta_cliente():
    form=SQLFORM(db.auth_user) 
    if form.accepts(request.vars, session):
        response.flash = "Registro agregado!"
    elif form.errors:
        response.flash = "Errores!"
    else:
        response.flash = "Completar!"
    return dict (f=form)
####################################
def altas_tranporte():
    form=SQLFORM(db.transporte, submit_button='Aceptar')
    if form.accepts(request.vars, session):
        response.flash = "Camion agregado"
    elif form.errors:
        response.flash = "Hubo errores"
    else:
        response.flash = "Complete formulario"
    return dict (f=form)
