# coding: utf8
# intente algo como
def index(): 

    return dict()


def realizar_altas():


    return dict()
def listar():
    consulta=db().select(db.articulo.articulo_id,  db.articulo.nombre, db.articulo.precio_Venta_Articulo)
    return dict (consulta=consulta)
