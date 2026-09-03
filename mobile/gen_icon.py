#!/usr/bin/env python3
"""Generate professional app icons (1024/512/adaptive) without any image libs.

Pure-Python PNG writer (RGBA, filter 0) + tiny software rasterizer for:
gradient background, a house glyph, and a bitmap "UTILITATI.MD" label.
Writes: icon.png (1024 app icon), and 512 icon.
"""
import zlib, struct, math

# ---------------------------------------------------------------- PNG writer

def write_png(path, w, h, px):
    """px: list of rows; each row a bytes of RGBA."""
    def chunk(typ, data):
        c = struct.pack('>I', len(data)) + typ + data
        c += struct.pack('>I', zlib.crc32(typ + data) & 0xffffffff)
        return c
    raw = b''.join(b'\x00' + row for row in px)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0)))
        f.write(chunk(b'IDAT', zlib.compress(raw, 9)))
        f.write(chunk(b'IEND', b''))

# ------------------------------------------------------------- raster helpers

def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def lerp(a, b, t):
    return tuple(round(a[i] + (b[i]-a[i])*t) for i in range(3))

BB = hex2rgb('#0f766e')  # bottom teal-dark
TT = hex2rgb('#2dd4bf')  # top teal-light
WHITE = (255, 255, 255)
GGOLD = (250, 204, 21)

class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        # rows of bytearray RGBA, transparent
        self.r = [[bytearray([0,0,0,0]) for _ in range(w)] for _ in range(h)]

    def set(self, x, y, rgb, alpha=255):
        if 0 <= x < self.w and 0 <= y < self.h:
            row = self.r[y][x]
            if alpha >= 255:
                row[0], row[1], row[2], row[3] = rgb[0], rgb[1], rgb[2], 255
            else:
                sa = alpha/255.0
                for i in range(3):
                    row[i] = round(row[i]*(1-sa) + rgb[i]*sa)
                row[3] = 255

    def fill_rect(self, x0, y0, x1, y1, rgb):
        for y in range(max(0,y0), min(self.h,y1+1)):
            for x in range(max(0,x0), min(self.w,x1+1)):
                self.set(x, y, rgb)

    def fill_tri(self, p0, p1, p2, rgb):
        ys = sorted([p0[1], p1[1], p2[1]])
        y0, y1 = max(0, ys[0]), min(self.h-1, ys[2])
        for y in range(y0, y1+1):
            xs = []
            for a, b in ((p0,p1),(p1,p2),(p2,p0)):
                if a[1] == b[1]: continue
                if min(a[1],b[1]) <= y <= max(a[1],b[1]):
                    xs.append(a[0] + (y-a[1])*(b[0]-a[0])/(b[1]-a[1]))
            if not xs: continue
            xs = sorted(xs)
            self.fill_rect(round(xs[0]), y, round(xs[-1]), y, rgb)

    def line(self, x0, y0, x1, y1, rgb, thick=1):
        n = max(abs(x1-x0), abs(y1-y0), 1)
        for i in range(n+1):
            t = i/n
            x, y = round(x0+(x1-x0)*t), round(y0+(y1-y0)*t)
            for dx in range(-(thick//2), thick//2+1):
                for dy in range(-(thick//2), thick//2+1):
                    self.set(x+dx, y+dy, rgb)

    def circle(self, cx, cy, r, rgb):
        for y in range(cy-r, cy+r+1):
            for x in range(cx-r, cx+r+1):
                if (x-cx)**2 + (y-cy)**2 <= r*r:
                    self.set(x, y, rgb)

    def to_rows(self):
        return [b''.join(bytes(pix) for pix in ch) for ch in self.r]

def draw_gradient(c, w, h):
    for y in range(h):
        t = y/(h-1)
        rgb = lerp(TT, BB, t)
        for x in range(w):
            c.r[y][x][0], c.r[y][x][1], c.r[y][x][2], c.r[y][x][3] = rgb[0], rgb[1], rgb[2], 255

# ------------------------------------------------------------- bitmap font 5x7
FONT = {
 'A':[0,1,1,1,1, 1,0,0,0,1, 1,0,0,0,1, 1,1,1,1,1, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1],
 'C':[0,1,1,1,1, 1,1,0,0,1, 1,0,0,0,0, 1,0,0,0,0, 1,1,0,0,1, 0,1,1,1,1, 0,0,0,0,0],
 'D':[1,1,1,1,0, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1, 1,1,1,1,0],
 'I':[0,0,1,1,0, 0,0,1,0,0, 0,0,1,0,0, 0,0,1,0,0, 0,0,1,0,0, 0,0,1,0,0, 0,1,1,1,0],
 'L':[1,0,0,0,0, 1,0,0,0,0, 1,0,0,0,0, 1,0,0,0,0, 1,0,0,0,0, 1,1,1,1,0, 0,0,0,0,0],
 'M':[1,0,0,0,1, 1,1,0,1,1, 1,0,1,0,1, 1,0,1,0,1, 1,0,0,0,1, 1,0,0,0,1, 1,0,0,0,1],
 '.':[0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,0,1,0, 0,0,0,1,0],
 ' ':[0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0, 0,0,0,0,0],
}

def draw_text(c, text, x, y, rgb, scale=1):
    cw, ch, gap = 6, 7, 2
    for ch_i in text:
        glyph = FONT.get(ch_i.upper())
        if glyph:
            for i, bit in enumerate(glyph):
                if bit:
                    gx = x + (i % 5)*scale
                    gy = y + (i // 5)*scale
                    c.fill_rect(gx, gy, gx+scale-1, gy+scale-1, rgb)
        x += cw*scale

# ------------------------------------------------------------- icon drawing

def build_icon(w, h, out):
    c = Canvas(w, h)
    draw_gradient(c, w, h)

    # soft ring highlight at top
    for yy in range(0, h//3):
        t = yy/(h//3)
        c.r[yy] = c.r[yy][:] if t < 0.001 else c.r[yy][:]
    # draw a subtle vignette circle
    c.circle(int(w*0.5), int(h*0.42), int(h*0.42), hex2rgb('#99f6e4'))
    # re-apply gradient over outer ring so only center pops
    for y in range(h):
        t = y/(h-1); rgb = lerp(TT, BB, t)
        for x in range(w):
            # inside circle keep lighter pop
            if (x-int(w*0.5))**2 + (y-int(h*0.42))**2 <= (int(h*0.40))**2:
                pass
            else:
                c.r[y][x][0], c.r[y][x][1], c.r[y][x][2] = rgb[0], rgb[1], rgb[2]

    # ---- house glyph (white, soft gold accent)
    cx = w*0.5
    # roof
    c.fill_tri((int(cx), int(h*0.16)), (int(w*0.12), int(h*0.42)), (int(w*0.88), int(h*0.42)), WHITE)
    # body
    c.fill_rect(int(w*0.20), int(h*0.41), int(w*0.80), int(h*0.66), WHITE)
    # door
    c.fill_rect(int(cx- w*0.08), int(h*0.50), int(cx+ w*0.08), int(h*0.66), GGOLD)
    # window cross on the sides
    c.line(int(w*0.30), int(h*0.50), int(w*0.30), int(h*0.60), WHITE, 3)
    c.line(int(w*0.70), int(h*0.50), int(w*0.70), int(h*0.60), WHITE, 3)

    # ---- label band
    label = "UTILITATI.MD"
    cw = 6*6  # scale 6
    tw = len(label)*cw
    x0 = int(w/2 - tw/2); y0 = int(h*0.74)
    draw_text(c, label, x0, y0, WHITE, scale=6)

    write_png(out, w, h, c.to_rows())
    print('wrote', out)

if __name__ == '__main__':
    build_icon(1024, 1024, 'icon.png')
    build_icon(512, 512, 'adaptive-icon.png')
    build_icon(1024, 1024, 'splash-icon.png')