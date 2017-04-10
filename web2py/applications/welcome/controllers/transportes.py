# coding: utf8
# intente algo como
def index(): return dict(message="hello from transportes.py")

def cargar_transporte():
    form=SQLFORM(db.transporte, submit_button='Aceptar')
    if form.accepts(request.vars, session):
        response.flash = "pedido agregado"
    elif form.errors:
        response.flash = "Hubo errores"
    else:
        response.flash = "Complete formulario" #este else es por si dieron aceptar sin cargar ningun dato
    return dict (form=form)
    

 
 
def mostrar_categarias():
    images = db(db.transporte,db.transporte.title).select()
    return dict(images=images) 
    
def show():  
    images = db.transporte(request.args(0)) or redirect(URL('mostrar_categarias')).select(
    imges.nro_motor,
    images.modelo,
    images.odometro_adquisicion,
    images.marca,
    images.tipo,
    images.seguro_compania,
    images.capacidad_carga
    )
    return dict(images=images)  
        
def download():
    return response.download(request, db)
def reporte_de_camiones():
    return dict(f=f)
