"""La ayuda en español (Ayuda > Cómo usar KanzonasSVG, F1): los mismos capítulos que HELP_HTML en
app.py, en el mismo orden. tests/test_i18n.py comprueba que nombra cada orden de los menús como
el menú la muestra en español."""

HELP_HTML_ES = """
<h2>KanzonasSVG</h2>
<p>KanzonasSVG convierte una imagen (un logotipo, un dibujo, un escaneo) en un archivo SVG:
formas en lugar de píxeles, nítidas a cualquier tamaño. Después puede editar el SVG en Inkscape,
Illustrator u otro editor vectorial.</p>
<p>Esta ayuda está en capítulos: haga clic en uno de la lista para ir a él. Escriba en el cuadro
de arriba (Ctrl+F) para buscar: se marcan todas las coincidencias, los capítulos que las tienen
muestran cuántas, e Intro (o F3) va a la siguiente, Mayús+Intro a la anterior. La ayuda puede
quedarse abierta mientras trabaja.</p>
<p>Los comandos están en la <b>cinta</b> de la parte superior de la ventana, en tres pestañas:
<b>Inicio</b> (abrir, guardar, Deshacer, Ajustes automáticos y las herramientas), <b>Imagen</b>
(las herramientas, las ediciones de color, el recorte y el borrador) y <b>Ver</b> (zoom, lo que se
muestra, ayuda). Los mismos comandos están en los menús, con los mismos nombres (los de la cinta
a veces son más cortos) y sus atajos. Pase el ratón sobre un botón para ver qué hace. Haga doble
clic en una pestaña, o use <i>Ver &gt; Contraer la cinta</i> (Ctrl+F1), para mostrar solo los
nombres de las pestañas; haga clic en una pestaña para abrirla de nuevo.</p>
<h3>Hacer un SVG</h3>
<ol>
<li><b>Abra una imagen</b>: <i>Archivo &gt; Abrir imagen...</i> (Ctrl+O), arrastre un archivo a
la ventana, o copie una imagen y use <i>Archivo &gt; Pegar imagen</i> (Ctrl+V).
<i>Archivo &gt; Abrir reciente</i> muestra las últimas 10 imágenes abiertas (<i>Vaciar la
lista</i> la vacía).</li>
<li><b>Revise los ajustes</b> de la derecha. Al abrir una imagen, KanzonasSVG elige los ajustes
que le convienen (vea <b>Ajustes automáticos</b> más abajo) y la traza. Cambie cualquier ajuste
y el SVG de la derecha se actualiza (salvo que <i>Trazar &gt; Actualizar automáticamente</i> esté
desactivado: entonces pulse <i>Trazar &gt; Actualizar ahora</i>, F5).</li>
<li><b>Guarde</b>: <i>Archivo &gt; Guardar como SVG...</i> (Ctrl+Mayús+S), <i>Archivo &gt; Guardar
como PDF...</i>, <i>Archivo &gt; Guardar como EPS...</i> o <i>Archivo &gt; Guardar como DXF...</i>
(en la cinta, <b>Guardar como</b> y su flecha; vea <b>Guardar</b> más abajo), o <i>Archivo &gt;
Copiar SVG</i> (Ctrl+Mayús+C) para pegarlo directamente en Inkscape u otro programa.</li>
</ol>
<h3>Las herramientas</h3>
<p>Lo que hace un clic o un arrastre sobre la imagen depende de la herramienta activa: una de
tres, en la cinta (<b>Herramientas</b>, en las pestañas Inicio e Imagen) y en el menú Trazar. La
barra encima de la imagen y del SVG dice qué hace la herramienta activa y tiene sus controles.
Esc vuelve a Seleccionar colores.</p>
<ul>
<li><i>Trazar &gt; Seleccionar colores</i> (activa al principio): un clic en la imagen o en el SVG
selecciona el color trazado ahí, Ctrl+clic selecciona más, y un arrastre mueve la imagen. Los
colores seleccionados se marcan en el SVG (todo lo demás atenuado) y la barra tiene <b>Cambiar
color</b>, <b>Combinar</b> y <b>Omitir</b> para ellos (vea <b>Editar colores</b>). Con el ratón
sobre la imagen, la barra de estado dice qué color selecciona un clic ahí. El clic derecho
muestra los comandos de color.</li>
<li><i>Trazar &gt; Recortar imagen</i> (Ctrl+R): arrastre sobre la parte de la imagen que quiere
trazar (vea <b>Recortar</b>). <b>Cancelar</b> en la barra, o Esc, la detiene.</li>
<li><i>Trazar &gt; Borrar en la imagen</i> (Ctrl+E): arrastre sobre la imagen para borrar lo que no
debe trazarse; un círculo muestra el borrador y su tamaño (vea <b>Borrar partes de la
imagen</b>). La barra tiene un control de <b>Tamaño</b>, <b>Restaurar la imagen</b> y
<b>Listo</b>.</li>
</ul>
<h3>Ajustes automáticos</h3>
<p>El botón <b>Ajustes automáticos</b> (o <i>Trazar &gt; Ajustes automáticos</i>, Ctrl+Mayús+A)
elige los ajustes para la imagen: cuántos colores necesita (los mínimos a partir de los cuales
más colores ya no la acercan visiblemente: un logotipo o una ilustración plana recibe
exactamente sus colores, hasta 64; una foto o una pintura, un número de hasta 16 que mantiene el
archivo razonable), <b>Suavizar</b> cuando tiene manchas de JPEG o ruido de escaneo,
<b>Fondo: Quitar</b> cuando su fondo es transparente (así el del SVG también lo es), y
<b>Blanco y negro</b> con su <b>Umbral</b> para un escaneo de líneas oscuras sobre una página
clara. Para <b>dibujos de líneas</b> (un plano, un dibujo o una captura de pantalla de uno:
líneas finas sobre un fondo liso) conserva los colores propios de las líneas, deja
<b>Suavizar</b> desactivado (borraría las líneas finas) y pone <b>Ampliar antes</b> en 4 veces,
para que las líneas de uno o dos píxeles se tracen como formas sólidas. También devuelve los
ajustes de curvas (<b>Motas</b>, <b>Suavizar esquinas</b>, <b>Optimizar</b>,
<b>Tolerancia</b>) a los valores que convienen a la imagen: Ajustes automáticos establece todos
los ajustes menos <b>Ajustar formas</b>, que se queda como usted lo puso. La barra de estado dice
qué eligió. Cambie lo que quiera después: los ajustes automáticos no lo deshacen.</p>
<p><i>Trazar &gt; Ajustes automáticos para imágenes nuevas</i> (activado al principio) hace esto
con cada imagen que abre o pega; desactívelo para conservar sus propios ajustes en cada imagen
nueva.</p>
<h3>Modos</h3>
<ul>
<li><b>Colores</b>: la imagen en unos pocos colores planos, una capa por color. Lo mejor para
logotipos. <b>Colores</b> fija cuántos (cuente también el fondo: un logotipo rojo sobre blanco
son 2).</li>
<li><b>Grises</b>: lo mismo en tonos de gris.</li>
<li><b>Escalones de brillo</b>: capas de gris según el brillo, de oscuro a claro.</li>
<li><b>Blanco y negro</b>: una forma negra para todo lo que es más oscuro que el
<b>Umbral</b>.</li>
<li><b>Bordes</b>: los contornos de las formas, encontrados por detección de bordes.</li>
<li><b>Autotrace: colores</b>: colores trazados con Autotrace en lugar de Potrace: curvas menos
numerosas y más sueltas.</li>
<li><b>Autotrace: línea central</b>: líneas por el centro de los trazos (escritura a mano,
dibujos de líneas) en lugar de contornos.</li>
</ul>
<h3>Ajustes</h3>
<ul>
<li><b>Suavizar</b>: iguala el ruido, las manchas de JPEG y la textura antes de elegir los
colores, manteniendo nítidos los bordes.</li>
<li><b>Apilar</b>: cada capa de color cubre también el área de las capas de encima, para que no
se vean huecos entre colores. Desactivado: las capas se colocan una al lado de otra.</li>
<li><b>Fondo</b>: <i>Conservar</i> traza el fondo como cualquier color. <i>Quitar</i> omite el
fondo de la imagen (su parte transparente cuando su borde la tiene; si no, el color que tiene la
mayor parte de su borde, claro u oscuro) alrededor de la imagen: el SVG es transparente ahí, y
ese color dentro de las formas (el blanco dentro de las letras de un logotipo) se queda.
<i>Quitar, también dentro</i> omite ese color en todas partes, así que los huecos dentro de las
formas también son transparentes. (Escalones de brillo: se omite la capa de abajo. Autotrace
siempre omite el blanco, o con Quitar, el color del fondo, en todas partes.)</li>
<li><b>Invertir</b>: traza las partes claras en lugar de las oscuras.</li>
<li><b>Motas</b>: elimina manchas de hasta este número de píxeles.</li>
<li><b>Suavizar esquinas</b>: 0 mantiene todas las esquinas en punta; más alto las redondea.</li>
<li><b>Optimizar</b>: une segmentos de curva (archivos más pequeños); <b>Tolerancia</b> es cuánto
puede mover eso la curva.</li>
<li><b>Ajustar formas</b> (desactivado al principio): los bordes casi rectos se vuelven rectas,
las líneas a menos de 1,5 grados de la horizontal o la vertical se vuelven exactamente
horizontales o verticales, y las formas redondas a menos de medio píxel de un círculo o de una
elipse (de ejes horizontal y vertical) se vuelven perfectas. Para máquinas de corte, láseres,
CAD y logotipos limpios: menos nodos, y las esquinas rectas siguen rectas. Puede mover un borde
hasta medio píxel e iguala un dibujo que era un poco irregular a propósito, así que lo activa
usted (los ajustes automáticos lo dejan como está). No en los modos de Autotrace.</li>
<li><b>Umbral de error</b> y <b>Pasadas de filtro</b> (Autotrace): cuánto se ciñen las curvas
al contorno, y cuánto se suavizan antes los contornos.</li>
<li><b>Conservar el grosor de las líneas</b> (línea central): da a cada línea el grosor que
tiene en la imagen.</li>
<li><b>Ampliar antes</b>: traza la imagen a 2 o 4 veces su tamaño, para curvas más suaves en
imágenes pequeñas. <i>Automático</i> hace 2 veces en imágenes de menos de 1000 píxeles. El SVG
conserva el tamaño de la imagen en todo caso. Una imagen nunca se amplía más allá de 40
megapíxeles (una imagen grande no gana nada con ello); la barra de estado dice cuánto se
amplió.</li>
</ul>
<p>Los ajustes se guardan para la próxima vez. <i>Trazar &gt; Restablecer ajustes</i> (o el botón
<b>Restablecer ajustes</b>) los devuelve todos a como empezaron.</p>
<p>Una imagen grande (de más de 3 megapíxeles) muestra primero una vista previa rápida, trazada a
partir de una copia más pequeña, mientras se traza la imagen entera; la barra de estado lo dice,
y <i>Guardar</i> y <i>Copiar SVG</i> esperan al SVG de la imagen entera.</p>
<h3>Editar colores</h3>
<p>En <b>Colores</b>, <b>Grises</b> y <b>Autotrace: colores</b>, el cuadro <b>Colores</b> muestra
los colores con los que se traza el SVG, una muestra cada uno. Haga clic en una muestra para
seleccionar su color, y Ctrl+clic en más para seleccionarlos también (Ctrl+clic en una
seleccionada la deselecciona). Hacer clic en la imagen o en el SVG hace lo mismo con el color
trazado ahí (con la herramienta <b>Seleccionar colores</b> activa): la barra de estado dice qué
color selecciona un clic antes de hacerlo. Los colores seleccionados se marcan en el SVG: todo lo
demás se atenúa hasta que no seleccione ninguno (<i>Colores &gt; No seleccionar ningún color</i>, o
Esc). Luego use los botones del cuadro Colores, de la barra encima de la imagen, de la pestaña
Imagen de la cinta, del menú Colores, o haga clic derecho en una muestra, en la imagen o en el
SVG:</p>
<ul>
<li><b>Cambiar color...</b> (<i>Colores &gt; Cambiar color...</i>) los traza con otro color que
usted elige: las formas se quedan, solo cambia su color.</li>
<li><b>Combinar</b> (<i>Colores &gt; Combinar colores...</i>) traza dos o más colores seleccionados
como un solo color, en una sola capa: elija cuál de ellos en la
lista que abre (el más grande primero), u <b>Otro color...</b>. Para una imagen con demasiados
tonos del mismo color, combine los tonos que no necesita separados. Los colores combinados se
muestran como una sola muestra.</li>
<li><b>Omitir</b> (<i>Colores &gt; Omitir</i>, Supr) los deja fuera: el SVG es transparente ahí
(una muestra tachada; selecciónela y use <b>Recuperar</b> para trazarla de nuevo, con su propio color;
<i>Edición &gt; Deshacer</i> devuelve un color que tenía antes).</li>
<li><b>Restablecer colores</b> (<i>Colores &gt; Restablecer colores</i>) deshace las ediciones de
los colores seleccionados, o de todos cuando no hay ninguno seleccionado.</li>
</ul>
<p>El <b>fondo</b> (el color alrededor de la imagen, o su parte transparente: lo que <b>Fondo:
Quitar</b> omite) tiene una muestra propia, con un marco discontinuo, aunque el mismo color esté
también dentro de la imagen (el blanco dentro de una letra): editar uno deja el otro como está.
Hacer clic en el fondo selecciona su muestra, y hacer clic en ese color dentro de la imagen, la
otra. (Las opciones <code>--recolor</code> y <code>--leave-out</code> de la línea de comandos
cambian un color en todas partes, también en el fondo.)</p>
<p>La imagen en sí nunca cambia, y las ediciones son para la imagen que se muestra: una imagen
nueva empieza sin ellas, y <i>Restablecer ajustes</i> las borra. Se siguen aplicando cuando se
eligen de nuevo los colores (otro número de colores, Suavizar, un recorte, Ajustes
automáticos): cada edición va al color más cercano a aquel en el que se hizo (a menos de 24
niveles). Una edición que ya no corresponde a ningún color se conserva, y el cuadro lo dice;
vuelve a aplicarse si ese color reaparece. La barra de estado dice cuántos colores están
editados. En la línea de comandos: <code>--list-colors</code>, <code>--recolor FROM=TO</code> y
<code>--leave-out COLOR</code>.</p>
<h3>Deshacer</h3>
<p><i>Edición &gt; Deshacer</i> (Ctrl+Z) vuelve al SVG anterior, tal como se trazó: sus ajustes,
ediciones de color y recorte. <i>Edición &gt; Rehacer</i> (Ctrl+Y, o Ctrl+Mayús+Z) avanza de
nuevo. Se puede volver a cualquier SVG trazado para la imagen que se muestra; un cambio hecho
después de Deshacer descarta lo que Rehacer habría devuelto, y una imagen nueva empieza de
cero.</p>
<h3>Recortar</h3>
<p>Para trazar solo una parte de una imagen (el dibujo de una captura de pantalla, sin las
barras de herramientas del programa alrededor; un logotipo de varios), use <i>Trazar &gt;
Recortar imagen</i> (Ctrl+R, o <b>Recortar</b> en la cinta) y arrastre sobre esa parte en el lado
izquierdo. Solo esa parte se
muestra y se traza, y el SVG tiene su tamaño; con <i>Ajustes automáticos para imágenes
nuevas</i> activado, los ajustes automáticos se eligen para esa parte (las barras de herramientas
de una captura pueden hacer que un dibujo le parezca otra cosa). Recorte de nuevo para recortar
más; Esc o <b>Cancelar</b> en la barra dejan de recortar antes de arrastrar. <i>Trazar &gt; Quitar recorte</i> (Ctrl+Mayús+R)
devuelve la imagen entera. La opción <code>--crop X,Y,W,H</code> de la línea de comandos hace lo
mismo.</p>
<h3>Guardar</h3>
<p>Elija el tipo de archivo con su comando: <i>Archivo &gt; Guardar como SVG...</i> (Ctrl+Mayús+S),
<i>Archivo &gt; Guardar como PDF...</i>, <i>Archivo &gt; Guardar como EPS...</i> o <i>Archivo &gt;
Guardar como DXF...</i> (en la cinta, <b>Guardar como</b> guarda el tipo que muestra, y su flecha
lista los cuatro: entonces muestra el último usado). Cada uno pregunta dónde, con la extensión del
nombre ya puesta. <i>Archivo &gt; Guardar...</i> (Ctrl+S) pregunta la primera vez (con el tipo
guardado la última vez), y luego guarda de nuevo en el mismo archivo.</p>
<ul>
<li><b>SVG</b>: para editores vectoriales (Inkscape, Illustrator, Affinity), máquinas de corte
(Cricut Design Space, Silhouette Studio) y páginas web.</li>
<li><b>PDF</b> y <b>EPS</b>: una página del tamaño de la imagen, en sus colores, para imprentas,
rotulistas, Illustrator y programas que no leen SVG.</li>
<li><b>DXF</b>: para programas de CAD, láser, CNC y corte de vinilo (LightBurn, AutoCAD, LibreCAD,
Fusion): los contornos de cada forma como líneas (las curvas se convierten en tramos rectos
cortos, a menos de 0,025 mm de ellas), una capa por color. Un DXF no puede guardar colores de
relleno, solo contornos, y no dice su unidad: está en milímetros, o en pulgadas cuando el
<b>Ancho al guardar</b> está en pulgadas, así que elija esa unidad cuando un programa la
pida.</li>
</ul>
<p>Cada color es un grupo propio, con el nombre de su color (una capa de Inkscape; en un DXF,
una capa como COLOR_B2002D): los programas que muestran los grupos listan los colores en lugar de
cientos de formas sueltas. (En los modos de Autotrace un color puede volver a aparecer encima de
otro, y recibe un segundo grupo, para que las formas sigan en su orden.)</p>
<p><b>Ancho al guardar</b> (en <b>Tamaño</b>) fija el tamaño del archivo: <i>Píxeles de la
imagen</i> conserva el tamaño propio de la imagen, 96 píxeles por pulgada (como los cuentan los
navegadores, Inkscape e Illustrator), o dé un ancho en <i>Pulgadas</i> o <i>Milímetros</i> y el
alto lo sigue. La línea de debajo muestra el tamaño que tendrán los archivos. Solo cambia lo que
se guarda (y se copia), no el trazado, y se conserva para la próxima vez.</p>
<h3>Borrar partes de la imagen</h3>
<p>Para dejar algo fuera del trazado (una marca de agua, una mancha, un texto junto a un
logotipo, una marca suelta), use <i>Trazar &gt; Borrar en la imagen</i> (Ctrl+E, o <b>Borrar</b>
en la cinta) y arrastre sobre ello en el lado izquierdo. Un círculo bajo el ratón muestra el
borrador, tan grande como lo que borra. Lo que arrastra se vuelve transparente, como el fondo de
una imagen transparente, y el SVG se actualiza al soltar. (Con <b>Fondo: Quitar</b> se omite; con
<b>Conservar</b>, una parte transparente se traza en blanco.) El control de <b>Tamaño</b> de la
barra encima de la imagen, <i>Trazar &gt; Borrador más pequeño</i> ([) y <i>Trazar &gt; Borrador
más grande</i> (]) cambian su tamaño; el botón central del ratón sigue moviendo la imagen.
<b>Listo</b> en la barra, Ctrl+E de nuevo o Esc dejan de borrar. <i>Edición &gt;
Deshacer</i> devuelve los trazos uno por uno, y <i>Trazar &gt; Restaurar la imagen</i>
(Ctrl+Mayús+E) devuelve todo lo borrado. El archivo de la imagen nunca cambia; una imagen nueva
empieza sin nada borrado. Borrar funciona también con un recorte (se conserva al recortar o al
quitar el recorte).</p>
<h3>Varias imágenes a la vez</h3>
<p><i>Archivo &gt; Convertir varias imágenes...</i> (Ctrl+Mayús+O) traza y guarda una lista de
imágenes de una vez. También se abre cuando elige varias imágenes en <i>Abrir imagen</i>, o
arrastra varias imágenes (o una carpeta) a la ventana. Añada imágenes con <b>Añadir
imágenes...</b>, <b>Añadir una carpeta...</b> (las imágenes que contiene, no los SVG) o
arrastrándolas a la lista, y luego elija:</p>
<ul>
<li><b>Ajustes</b>: <i>Ajustes automáticos para cada imagen</i> (cada una recibe los ajustes que
le convienen, como al abrirla, con <b>Ajustar formas</b> como usted lo puso), o <i>Los ajustes
que se ven ahora</i>, los mismos para todas (no las ediciones de color, que son para la imagen
que se muestra, ni su recorte).</li>
<li><b>Guardar como</b>: SVG, PDF, EPS o DXF, con el <b>Ancho al guardar</b> fijado en Tamaño
(todas las imágenes con ese ancho, o cada una con su propio tamaño en píxeles).</li>
<li><b>Guardar en</b>: junto a cada imagen, con su nombre, o en una carpeta. Los archivos que ya
existen se saltan salvo que <b>Reemplazar los archivos que ya existen</b> esté activado.</li>
</ul>
<p><b>Convertir</b> empieza; la lista dice qué pasó con cada imagen (guardada, con sus formas y
nodos; saltada; o por qué falló, y la siguiente se hace igualmente). <b>Detener</b> para en el
acto (la imagen que se está trazando no se guarda, y las demás no se hacen). <b>Abrir la
carpeta</b> muestra los archivos. La ventana sigue usable mientras trabaja. La línea de comandos
hace lo mismo para scripts.</p>
<h3>Verlo</h3>
<p>Encima del SVG: su tamaño, tal como Guardar escribe un SVG, cuántas formas tiene y cuántos
<b>nodos</b> (los puntos por los que pasan sus contornos; una máquina de corte gira en cada uno,
y con menos corta más limpio: suba <b>Tolerancia</b>, <b>Suavizar esquinas</b> o <b>Motas</b>, o
use menos colores, para tener menos). La barra de estado dice lo mismo.</p>
<p>El lado izquierdo muestra la imagen; <i>Ver &gt; Mostrar los colores a trazar</i> (Ctrl+T) la
muestra con sus colores reducidos, tal como se trazará. <i>Ver &gt; Mostrar contornos</i>
(Ctrl+L) muestra el SVG como sus contornos, líneas oscuras finas, con sus nodos como cuadraditos
azules (con un zoom del 150% o más, o cuando no hay más de 3.000): para ver por dónde irá una
máquina de corte, y qué cambian Ajustar formas, Tolerancia y Motas. Los dos lados se acercan y se
mueven juntos: la rueda del ratón mueve la imagen arriba y abajo (Mayús+rueda: a los lados),
Ctrl+rueda hace zoom, y un arrastre la mueve. <i>Ver &gt; Ajustar a la ventana</i> (Ctrl+0),
<i>Ver &gt; Tamaño real</i> (Ctrl+1), <i>Ver &gt; Acercar</i> (Ctrl++), <i>Ver &gt; Alejar</i>
(Ctrl+-).</p>
<p>La rueda desplaza el panel de ajustes incluso sobre un número o una lista: estos cambian con la
rueda solo después de hacer clic en ellos.</p>
<h3>Atajos de teclado</h3>
<table cellpadding="2">
<tr><td>Ctrl+O</td><td>Abrir imagen</td></tr>
<tr><td>Ctrl+Mayús+O</td><td>Convertir varias imágenes</td></tr>
<tr><td>Ctrl+V</td><td>Pegar imagen</td></tr>
<tr><td>Ctrl+S</td><td>Guardar</td></tr>
<tr><td>Ctrl+Mayús+S</td><td>Guardar como SVG</td></tr>
<tr><td>Ctrl+Mayús+C</td><td>Copiar SVG</td></tr>
<tr><td>F5</td><td>Actualizar ahora</td></tr>
<tr><td>Ctrl+Mayús+A</td><td>Ajustes automáticos</td></tr>
<tr><td>Ctrl+Z / Ctrl+Y</td><td>Deshacer / Rehacer</td></tr>
<tr><td>Ctrl+clic</td><td>Seleccionar más colores (una muestra, la imagen o el SVG)</td></tr>
<tr><td>Supr</td><td>Omitir (los colores seleccionados)</td></tr>
<tr><td>Esc</td><td>Volver a Seleccionar colores; después, no seleccionar ningún color</td></tr>
<tr><td>Ctrl+R / Ctrl+Mayús+R</td><td>Recortar imagen / Quitar recorte</td></tr>
<tr><td>Ctrl+T</td><td>Mostrar los colores a trazar</td></tr>
<tr><td>Ctrl+L</td><td>Mostrar contornos</td></tr>
<tr><td>Ctrl+E / Ctrl+Mayús+E</td><td>Borrar en la imagen / Restaurar la imagen</td></tr>
<tr><td>[ / ]</td><td>Borrador más pequeño / Borrador más grande</td></tr>
<tr><td>Ctrl+0 / Ctrl+1</td><td>Ajustar a la ventana / Tamaño real</td></tr>
<tr><td>Ctrl++ / Ctrl+-</td><td>Acercar / Alejar</td></tr>
<tr><td>Ctrl+rueda / rueda</td><td>Zoom / mover la imagen (Mayús+rueda: a los lados)</td></tr>
<tr><td>Ctrl+F1</td><td>Contraer la cinta</td></tr>
<tr><td>F1</td><td>Cómo usar KanzonasSVG</td></tr>
<tr><td>Ctrl+Q</td><td>Salir</td></tr>
</table>
<h3>Línea de comandos</h3>
<p>El mismo trazado funciona desde un símbolo del sistema, para muchos archivos a la vez (en
Windows, <code>kanzonassvg-cli.exe</code> en la carpeta del programa). Ejecútelo con
<code>--help</code> para ver todas las opciones (en inglés: la línea de comandos siempre está en
inglés), por ejemplo:<br>
<code>kanzonassvg-cli --colors 4 *.png -o svgs</code><br>
<code>kanzonassvg-cli logo.png -o logo.dxf --width 100mm</code> (la extensión elige el tipo;
<code>--format pdf</code> para muchos archivos; <code>--width</code> en <code>in</code> o
<code>mm</code>)</p>
<h3>Idioma</h3>
<p><i>Ver &gt; Idioma</i>: <i>Automático (el del sistema)</i>, <i>English</i> o <i>Español</i>.
KanzonasSVG cambia la próxima vez que se abre (sus menús, ajustes, mensajes, esta ayuda, y los
botones y cuadros de diálogo propios de Qt). La línea de comandos siempre está en inglés.</p>
<h3>Actualizaciones</h3>
<p>Una vez al día, unos segundos después de abrirse, KanzonasSVG pregunta a GitHub si hay una
versión más nueva (<i>Ayuda &gt; Buscar actualizaciones automáticamente</i>, activado al
principio; no envía nada sobre usted ni sobre sus imágenes, y cuando no hay conexión simplemente
lo intenta de nuevo al día siguiente). Cuando la hay, un aviso en la barra de estado lo dice:
<b>Novedades</b> muestra lo que cambió desde su versión (las notas están en inglés),
<b>Actualizar ahora</b> la actualiza, <b>Descargar</b> abre la página de la versión, <b>Omitir
esta versión</b> deja de avisar de esa versión, y <b>Más tarde</b> oculta el aviso.
<i>Ayuda &gt; Buscar actualizaciones...</i> pregunta en el acto.</p>
<p><b>Actualizar ahora</b> descarga la versión nueva, la comprueba con la suma de verificación que
GitHub publica con la versión (no se instala nada si no coinciden), cierra KanzonasSVG, pone la
versión nueva en su lugar y lo abre de nuevo. Instalado con el instalador, ejecuta el instalador
nuevo sobre este; descomprimido de KanzonasSVG-windows.zip, reemplaza los archivos del programa en
esa carpeta; la AppImage de Linux reemplaza su archivo. Sus ajustes se conservan. (Ejecutado desde
su código fuente, KanzonasSVG solo lo avisa.) Nunca se descarga ni se instala nada hasta que hace
clic en <b>Actualizar ahora</b>.</p>
<h3>Acerca de</h3>
<p><i>Ayuda &gt; Acerca de KanzonasSVG</i> muestra la versión, de dónde viene el trazado y la
licencia.</p>
"""
