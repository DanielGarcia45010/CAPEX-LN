def densify_geometry(geom, step=0.001):

    try:

        if geom.geom_type == "Point":
            yield geom.x, geom.y

        elif geom.geom_type == "LineString":

            length = geom.length
            n = max(2, int(length / step))

            for i in range(n):
                p = geom.interpolate(i / (n - 1) * length)
                yield p.x, p.y

        elif geom.geom_type == "Polygon":
            yield from densify_geometry(geom.boundary, step)

    except:
        return