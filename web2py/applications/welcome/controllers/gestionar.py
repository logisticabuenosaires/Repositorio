############################################################################################################
# Este controlador contiene las paginas del DESPACHADOR, se necesita estar logueado como tal para poder navegar.
############################################################################################################
#@auth.requires_login()
def index():
   response.flash = "ORGANICE SU REPARTO!"    
   return dict()

############################################################################################################

   
def user():
    return dict(form=auth())

############################################################################################################

def download():
    return response.download(request,db)

############################################################################################################


def call():
    session.forget()
    return service()        
#####################
def buscar_cliente():
    form = SQLFORM.factory(
        Field("cliente_id", db.auth_user, default=auth.user_id, 
        requires = IS_IN_DB(db, db.auth_user.id, "(%(id)s) %(first_name)s %(last_name)s")))
    if form.accepts(request.vars, session):
        cliente = db(db.auth_user.id==form.vars.cliente_id).select().first()
        if cliente: # lo encontre?
            session.cod_cli  = cliente.cod_cli ,
            session.pedidos = []
            redirect(URL('verificar_existencia'))
        else:
            response.flash = "cliente no encontrado"
    return dict(form=form)

def verificar_existencia():
    # recibo session.cod_cli
    form = SQLFORM.factory(
        Field('cod_art', 'integer'),
        Field('cant', 'integer'),
        )
    if form.accepts(request.vars, session):
        art = db(db.articulo.codigo_Articulo==form.vars.cod_art).select().first()
        if not art:
            response.flash = "articulo no encontrado"
        else:
            existencia = db(db.articulo.codigo_Articulo==form.vars.cod_art).select(
                            db.articulo.codigo_Articulo.sum().with_alias("suma")).first()
            if not existencia or existencia.suma<=form.vars.cant:
                response.flash = "no hay en existencia"
            else:
                # voy agregando los articulos y cantidades pedidas
                session.pedidos.append({'.codigo_Articulo': form.vars.cod_art,
                                        'cantidad': form.vars.cant,
                                        'precio_Venta_Articulo': art.precio})
    return dict(form=form)                                

    
def imprimir_factura():
    nro_fact = request.vars['nro_fact']
    # buscar factura
    fact = db(db.factura.nro_fact==nro_fact).select().first()
    # buscar cliente
    cli = db(db.auth_user.cod_cli).select().first()
    # busco ventas
    datos_venta = []
    for venta in db(db.factura.nro_fact==nro_fact).select():
        # busco el articulo
        art = db(articulo.codigo_Articulo==venta.cod_art).select().first()
        datos_venta.append({
            'cod_art': venta.cod_art,
            'importe': venta.importe,
            'cant': venta.cant,
            'descripcion': art.descripcion,
            })
    factura_impresa = {
         'nro_fact': nro_fact,
 #        'cod_cli': fact.cod_cli,
         'nombre_cliente': cli.nombre,
         'domicilio_cliente': cli.domicilio,
         'total': fact.total,
         'datos_ventas': datos_venta
         } 
    return factura_impresa
def imprimir_pedido():
  

    pedido_id =request.args[0]
    # Busca el pedido para mostrarlo
    pedido = db(db.sale.id==pedido_id,db.sale.product==pedido_id).select()[0]
     
    cliente = db(db.auth_user.id==pedido.buyer).select()[0]
    chofer = db(db.chofer.id==pedido.asignar_chofer).select()[0]
  
    localidad_destino = db(db.sale.shipping_city==pedido.shipping_city).select()[0]

    producto = db(db.articulo.nombre).select()[0]

    cantidad = db(db.sale.quantity==pedido.quantity).select()[0]
    return dict(
    pedido=pedido,
    cliente=cliente,
    chofer=chofer,
    localidad_destino= localidad_destino,
    producto=producto,
    cantidad=cantidad
     )
