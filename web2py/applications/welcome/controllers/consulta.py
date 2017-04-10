# coding: utf8
# try something like
def index(): return dict(message="hello from consulta.py")
def buscar_cliente():
    form = SQLFORM.factory(
        Field('nombre_cliente', 'string'),
        )
    if form.accepts(request.vars, session):
        cliente = db(db.lista_clientes.nro_doc==form.vars.nombre_cliente).select().first()
        if cliente: # lo encontre?
            session.user_id=cliente.user_id
            session.pedidos = []
            redirect(URL('verificar_existencia'))
        else:
            response.flash = "cliente no encontrado"
    return dict(form=form)

def verificar_existencia():
    # recibo session.cod_cli
    form = SQLFORM.factory(
        Field('codigo_Articulo', 'integer'),
        Field('cantidad', 'integer'),
        )
    if form.accepts(request.vars, session):
        art = db(db.articulo.codigo_Articulo==form.vars.codigo_Articulo).select().first()
        if not art:
            response.flash = "articulo no encontrado"
        else:
            existencia = db(db.stock.cod_art==form.vars.cod_art).select(
                            db.stock.cantidad.sum().with_alias("suma")).first()
            if not existencia or existencia.suma<=form.vars.cant:
                response.flash = "no hay en existencia"
            else:
                # voy agregando los articulos y cantidades pedidas
                session.pedidos.append({'cod_art': form.vars.cod_art,
                                        'cant': form.vars.cant,
                                        'precio_Venta_Articulo':articulo.precio_Venta_Articulo})
    return dict(form=form)
