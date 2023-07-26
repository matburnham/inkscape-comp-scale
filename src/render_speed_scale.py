#!/usr/bin/env python
# coding=utf-8
'''
Copyright (C)
2009 Sascha Poczihoski, sascha@junktech.de
Original author.

2013 Roger Jeurissen, roger@acfd-consultancy.nl
Added dangling labels and inside/outside scale features.

2015 Paul Rogalinski, pulsar@codewut.de
Adapted Inkscape 0.91 API changes.

2015 Bit Barrel Media, bitbarrelmedia -at- gmail dot com
-Changed UI and added the following features:
	Label offset. This will move the labels side to side and up/down.
	Option to use the center of a bounding box as the drawing reference.
	Ability to set line stroke width.
	Option to add a perpendicular line.
	Mathematical expression for the number format. For example, to divide the label number by 2, use "n/2".
	"Draw all labels" checkbox.
	Option to flip the label orientation.
	Support for "Draw every x lines" = 0 in order to remove lines.

2020 Neon22 github
- migrated to inkscape 1.0
- fixed font adjustments for flipping, inverting, etc
- fixed 360 degree circulars
- fixed centering on selected items
- added internal docs
- clarified UI, words, values
- improved groupings
- cleaned up params affected by units
- fixed perplines for invert
- help tab

2023 matburnham github
- codebase significantly diverged
- significantly modified code to draw speed scale rulers (e.g. 0.75mm/km)

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

#for debugging:
message = "Debug: " + str(i) + "\n"
inkex.debug(message)
'''

import inkex
from inkex import Style, Line, PathElement, DirectedLineSegment, Vector2d, units
from inkex.paths import Path, Move, Line
from simplestyle import *
from lxml import etree

import sys, math

# a dictionary of unit to user unit conversion factors
CONVERSIONS = {
    'kts': 1.852,
    'mph': 1.609,
    'kph': 1.0,
}

def convert_speed_to_kph(value, from_unit):
    """Returns kph value for speed passed."""
    return value * CONVERSIONS[from_unit]

def max_decimal_digits(value, digits=2):
	"""Return a (specified) maximum number of decimal digits, ignoring any
	trailing zero or decimal point.
	"""
	return ('{:0.{}f}'.format(value, digits)).rstrip('0').rstrip('.')

class Arrow():
    def __init__(self, L, A, start_type, style_ratio, sty):
        self.L = L
        self.A = A
        self.start_type = start_type
        self.style_ratio = style_ratio
        self.sty = sty
        self.new_sty = Style({'stroke': 'none', 'stroke-width':'0', 
            'fill': sty['stroke']})

    def cal_points(self, lineseg):
        L, A, offset = (self.L, self.A, self.style_ratio)
        line_vec = lineseg.vector
        side_length = L * math.tan(math.radians(A) / 2)
        side_vec1 = Vector2d(-1 * line_vec.y, line_vec.x) / line_vec.length * \
                    side_length
        side_vec2 = Vector2d(line_vec.y, -1 * line_vec.x) / line_vec.length * \
                    side_length
        pt_start = lineseg.start
        pt_on_line = Vector2d(lineseg.point_at_length(L))
        pt_offset = Vector2d(lineseg.point_at_length(L * (1 - offset)))
        pt_side1 = pt_on_line + side_vec1
        pt_side2 = pt_on_line + side_vec2
        return (pt_start, pt_side1, pt_offset, pt_side2)

    def add_arrow(self, lineseg, parent):
        pts = self.cal_points(lineseg)
        elem = self.create_arrow(*pts)
        parent.add(elem)

    def create_arrow(self, point1, point2, point3, point4):
        name = 'arrowhead'
        elem = inkex.PathElement()
        elem.update(**{
            'style': self.new_sty,
            'inkscape:label': name,
            'd': 'M ' + str(point1.x) + ',' + str(point1.y) +
                ' L ' + str(point2.x) + ',' + str(point2.y) +
                ' L ' + str(point3.x) + ',' + str(point3.y) + 
                ' L ' + str(point4.x) + ',' + str(point4.y) + 
                ' z'})
        return elem

class NewPath():
    def __init__(self, pathelem, arrow):
        self.pathelem = pathelem
        self.arrow = arrow
        self.style = pathelem.style.copy()
        self.path = pathelem.path.to_absolute()
        self.start_type = arrow.start_type 

    def line_width(self):
        try:
            line_wid = units.parse_unit(self.style['stroke-width'])[0]
        except:
            line_wid = 0.264583 #self.svg.unittouu('1px')   ### This does not have svg
        return line_wid

    def start_end(self):
        path = self.path
        start, end = path[0].args, path[1].args
        if len(end) == 1: # handle H and V
            end = path[1].to_line(path[0]).args
        return (Vector2d(start), Vector2d(end))

    def multi_segments(self):
        start, end = self.start_end()
        line = DirectedLineSegment(start, end)
        start = self.cal_shorten_point(line)
        self.path[0] = Move(start.x, start.y)
        pathelem_new = PathElement.new(self.path)
        pathelem_new.style = self.arrow.sty
        self.pathelem.replace_with(pathelem_new)
        return pathelem_new

    def cal_shorten_point(self, lineseg):
        linewidth = self.line_width()
        A = self.arrow.A
        side_length = linewidth / 2
        offset_length = side_length / math.tan(math.radians(A) / 2)
        offset = offset_length + linewidth
        pt_on_line = Vector2d(lineseg.point_at_length(offset))
        return pt_on_line

    def new_pathelem(self):
        start, end = self.start_end()

        if self.start_type == 'start':
            line = DirectedLineSegment(start, end)
            start = self.cal_shorten_point(line)
            npath = self.new_path(start, end)
            self.pathelem.replace_with(npath)
            return npath
        elif self.start_type == 'end':
            line = DirectedLineSegment(end, start)
            end = self.cal_shorten_point(line)
            npath = self.new_path(start, end)
            self.pathelem.replace_with(npath)
            return npath
        else:
            line = DirectedLineSegment(start, end)
            start_new = self.cal_shorten_point(line)
            line = DirectedLineSegment(end, start)
            end_new = self.cal_shorten_point(line)
            npath = self.new_path(start_new, end_new)
            self.pathelem.replace_with(npath)
            return npath

    def new_arrow(self, parent):
        start, end = self.start_end()
        starttype = self.start_type
        if starttype == 'start' or starttype == 'both':
            line = DirectedLineSegment(start, end)
            self.arrow.add_arrow(line, parent)
        if starttype == 'end' or starttype == 'both':
            line = DirectedLineSegment(end, start)
            self.arrow.add_arrow(line, parent)     

    def new_path(self, start, end):
        # this is similar to draw_SVG_tri, but uses new classes in inkex
        # This code is probably easier to understand
        path = Path()
        path.append([Move(start.x, start.y), Line(end.x, end.y)] )
        pathelem = PathElement.new(path)
        pathelem.style = self.style
        return pathelem

class ScaleGen(inkex.Effect):

	def __init__(self):

		# Call the base class constructor.
		inkex.Effect.__init__(self)

		# Page 1 (Shape)
		self.arg_parser.add_argument('--speed',
			type = int, dest = 'speed', default = '60',
			help = 'Speed:')
		self.arg_parser.add_argument('--speed-unit',
			type = str, dest = 'speed_unit', default = 'kts',
			help = 'Unit:')
		self.arg_parser.add_argument('--scale',
			type = int, dest = 'scale', default = '250000',
			help = 'Scale:')
		self.arg_parser.add_argument('--max-length',
			type = int, dest = 'max_length', default = '280',
			help = 'Max length:')
		self.arg_parser.add_argument('-u', '--unit',
			type = str, dest = 'unit', default = 'mm',
			help = 'Unit:')
		self.arg_parser.add_argument('--useref',
			type = inkex.Boolean, dest = 'useref', default = 'False',
			help = 'Reference is bounding box center')
		self.arg_parser.add_argument('--insidetf',
			type = inkex.Boolean, dest = 'insidetf', default = 'False',
			help = 'Draw lines above or below line')
		#
		self.arg_parser.add_argument('-s', '--fontsize',
			type = float, dest = 'fontsize', default = '3',
			help = 'Font Height')
		self.arg_parser.add_argument('-i', '--suffix',
			type = str, dest = 'suffix', default = ' ',
			help = 'Appended to label')
		# label offset
		self.arg_parser.add_argument('-x', '--labeloffseth',
			type = float, dest = 'labeloffseth', default = '0.0',
			help = 'Label offset in X')
		self.arg_parser.add_argument('-y', '--labeloffsetv',
			type = float, dest = 'labeloffsetv', default = '7.0',
			help = 'Label offset in Y')
			
		## Page 3 (Lines)
		self.arg_parser.add_argument('--perplinestrokewidth',
			type = float, dest = 'perplinestrokewidth', default = '0.2',
			help = 'Perpendicular line - Stroke width')
		self.arg_parser.add_argument('--perplineoffset',
			type = float, dest = 'perplineoffset', default = '0',
			help = 'Offset')
		#
		self.arg_parser.add_argument('--textlinestrokewidth',
			type = float, dest = 'textlinestrokewidth', default = '2.5',
			help = 'Text line - Stroke width for background')
		self.arg_parser.add_argument('--textlineoffset',
			type = float, dest = 'textlineoffset', default = '2',
			help = 'Offset')
		#
		self.arg_parser.add_argument('-g', '--labellinelength',
			type = float, dest = 'labellinelength', default = '100',
			help = 'Length of main Label line')
		self.arg_parser.add_argument('--labellinestrokewidth',
			type = float, dest = 'labellinestrokewidth', default = '0.4',
			help = 'Stroke width of main Label line')
		#
		self.arg_parser.add_argument('-v', '--mark2wid',
			type = int, dest = 'mark2wid', default = '70',
			help = 'Short line: - Length (units): (\%):')
		self.arg_parser.add_argument('--shortlinestrokewidth',
			type = float, dest = 'shortlinestrokewidth', default = '0.2',
			help = 'Short line - Stroke width')
        #
		self.arg_parser.add_argument('--dimensionoffset',
            type = int, dest = 'dimensionoffset', default='10',
            help = 'Dimension offset')
		#
		self.arg_parser.add_argument('--arrow-style',
			type = str, dest = 'arrow_style', default = 'sharp',
			help = 'Arrow style')
		self.arg_parser.add_argument('--arrow-len',
			type = int, dest = 'arrow_len', default = '10',
			help = 'Arrow length')
		self.arg_parser.add_argument('--arrow-angle',
			type = int, dest = 'arrow_angle', default = '30',
			help = 'Arrow angle')

		#dummy for the doc tab - which is named
		self.arg_parser.add_argument("--tab",
			dest = "tab", default="use",
			help = "The selected UI-tab when OK was pressed")

	def speed_max_digits(self, unit_to, digits=2):
		"""Return the speed converted to the specified units with a (specified)
		maximum number of decimal digits, ignoring any trailing zero or decimal
		point.
		"""
		return max_decimal_digits(self.speed * CONVERSIONS[self.speed_unit] / CONVERSIONS[unit_to], digits)
        
	def add_box(self, x, y, w):
		"""Add a box background behind text to make it clearer. Unfortunately
        inkex doesn't know how wide will be once rendered, so we have to guess.
        
        """
		name = 'background_box'
		strokewidth = self.textlinestrokewidth
		y2 = y1 = y + strokewidth/2
		line_style = {
			'stroke': 'white',
			'stroke-width': strokewidth,
		}

		x1 = x-w/2
		x2 = x+w/2
		
		x1 = str(x1)
		y1 = str(y1)
		x2 = str(x2)
		y2 = str(y2)

		line_attribs = {
			'style' : str(inkex.Style(line_style)),
			inkex.addNS('label','inkscape') : name,
			'd' : 'M '+x1+','+y1+' L '+x2+','+y2
		}
		line = etree.SubElement(self.blank_out_text, inkex.addNS('path','svg'), line_attribs )

	def add_label(self, value, x, y, group, colour):
		"""Add arbitrary text"""
		font_height_offset = self.svg.unittouu(str(self.fontsize)+"mm")
		x = float(x)
		y = float(y) + font_height_offset

		text = etree.SubElement(group, inkex.addNS('text','svg'))
		text.text = value
		style = {
            'text-align' : 'center',
        	'text-anchor': 'middle', 'font-size': str(self.fontsize),
			'fill': colour
        }
		text.set('style', str(inkex.Style(style)))
		text.set('x', str(float(x)))
		text.set('y', str(float(y)))
		group.append(text)

	def add_numeric_label(self, n, x, y, group, fontsize):
		""" draw text at x,y location
		"""
		number = int(n/6)
		self.add_label(str(number), x, y, group,
			'red' if number%2==0 else 'black')


	def add_straight_line(self, i, groups):
		""" Used for straight line graphs.
			add_numeric_label() is called from inside
		"""

		label = False
		arrow = False
		x = i*self.res

		if i % 6 == 0:
			name = 'label_line_{}'.format(i)
			line_style = {
				'stroke': 'red' if i%12==0 else 'black',
		 		'stroke-width': self.labellinestrokewidth,
			}
			y1 = -self.labellinelength
			y2 = self.labellinelength * self.mark2wid
			group = groups[0]
			label = True
			arrow = True
		else:
			name = 'short_line_{}'.format(i)
			line_style = {
				'stroke': 'red' if i%6==3 else 'black',
				'stroke-width': self.shortlinestrokewidth
			}
			y1 = 0
			y2 = self.labellinelength * self.mark2wid
			group = groups[1]

		x1 = str(x)
		y1 = str(y1)
		x2 = str(x)
		y2 = str(y2)

		line_attribs = {
			'style' : str(inkex.Style(line_style)),
			inkex.addNS('label','inkscape') : name,
			'd' : 'M '+x1+','+y1+' L '+x2+','+y2
		}

		line = etree.SubElement(group, inkex.addNS('path','svg'), line_attribs )

		if arrow:
			L = self.svg.unittouu(str(self.arrow_len) + 'px')
			A = self.arrow_angle
			start_type = 'end'
			style_type = self.options.arrow_style
			style_ratio = 0.0 if style_type == 'normal' else .25

			arrow = Arrow(L, A, start_type, style_ratio, line.style)
			newpath = NewPath(line, arrow)
			newpath.new_arrow(group)
			newpath.new_pathelem()

		if label:
			self.add_numeric_label(i, x2, -self.labeloffsetv, groups[4], self.fontsize)


	def add_perpendicular_line(self, type, group):
		""" Add a horizontal line
		"""

		name = 'perpendicular_line'
		strokewidth = self.perplinestrokewidth
		line_style = {
			'stroke': 'black',
			'stroke-width': strokewidth,
		}

		if type == 0: # basic line 
			y2 = y1 = self.perplineoffset
		elif type == 1: # basic line - top 
			y2 = y1 = self.perplineoffset - self.labellinelength
		else: # white background behind text
			strokewidth = self.textlinestrokewidth
			y2 = y1 = -self.labeloffsetv + strokewidth/2
			line_style = {
				'stroke': 'white',
				'stroke-width': strokewidth
			}			

		strokeoffset = (strokewidth / 2)
		x2 = ((self.scaleto-1)*self.res) + strokeoffset*2 # RHS of horiz line
		x1 = ((self.scalefrom)*self.res) - strokeoffset   # LHS of horiz line

		x1 = str(x1)
		y1 = str(y1)
		x2 = str(x2)
		y2 = str(y2)

		line_attribs = {
			'style' : str(inkex.Style(line_style)),
			inkex.addNS('label','inkscape') : name,
			'd' : 'M '+x1+','+y1+' L '+x2+','+y2
		}
		line = etree.SubElement(group, inkex.addNS('path','svg'), line_attribs )

	def add_dimensions(self, group):
		""" Add text specifying dimensions to ruler.
		"""
		kph = self.speed_max_digits('kph')
		mph = self.speed_max_digits('mph')
		kts = self.speed_max_digits('kts')

		one_km_mm = 1 / self.scale * 1000 * 1000
		# TODO: use a better conversion function
		one_mi_mm = max_decimal_digits(one_km_mm / CONVERSIONS['kph'] * CONVERSIONS['mph'])
		one_kt_mm = max_decimal_digits(one_km_mm / CONVERSIONS['kph'] * CONVERSIONS['kts'])

		x = (self.scaleto-self.scalefrom)/2*self.res
		xa = self.scalefrom * self.res + 50
		xb = self.scaleto * self.res - 70

		y = self.labeloffsetv - self.dimensionoffset

		text = '{}kph   {}mph   {}kts   1:{}K'.format(kph, mph, kts, int(self.scale/1000))
		self.add_label(text, xa, y, group, 'black')
		self.add_box(xa,y,40)

		text = '1 min={}mm   1km={}mm  1mi={}mm  1nm={}mm'.format(max_decimal_digits(self.mm_per_min), one_km_mm, one_mi_mm, one_kt_mm)
		self.add_label(text, xb, y, group, 'black')
		self.add_box(xb,y,65)
                
### Main function
	def effect(self):
		# Values from UI corrected for units etc.
		self.speed     = self.options.speed
		self.speed_unit= self.options.speed_unit
		self.scale     = self.options.scale
		self.max_length= self.options.max_length
		#
		self.unit      = self.options.unit
		self.useref    = self.options.useref	# bool
		self.insidetf  = self.options.insidetf	# bool
		#
		self.fontsize     = self.svg.unittouu(str(self.options.fontsize)+"pt")	# all font calcs in pts
		self.suffix       = self.options.suffix
		self.labeloffseth = self.svg.unittouu(str(self.options.labeloffseth)+self.unit)
		self.labeloffsetv = self.svg.unittouu(str(self.options.labeloffsetv)+self.unit)
		#
		self.perplinestrokewidth = self.svg.unittouu(str(self.options.perplinestrokewidth)+self.unit)
		self.perplineoffset      = self.svg.unittouu(str(self.options.perplineoffset)+self.unit)
		#
		self.textlinestrokewidth = self.svg.unittouu(str(self.options.textlinestrokewidth)+self.unit)
		self.textlineoffset      = self.svg.unittouu(str(self.options.textlineoffset)+self.unit)
		#
		self.labellinelength      = self.svg.unittouu(str(self.options.labellinelength)+self.unit)
		self.labellinestrokewidth = self.svg.unittouu(str(self.options.labellinestrokewidth)+self.unit)
		#
		self.mark2wid             = self.options.mark2wid / 100
		self.shortlinestrokewidth = self.svg.unittouu(str(self.options.shortlinestrokewidth)+self.unit)
        #
		self.dimensionoffset     = self.svg.unittouu(str(self.options.dimensionoffset)+self.unit)
        #
		self.arrow_style = self.options.arrow_style
		self.arrow_len   = self.options.arrow_len
		self.arrow_angle = self.options.arrow_angle

		# Get access to main SVG document element and get its dimensions.
		doc = self.document.getroot()

		# Again, there are two ways to get the attributes:
		# width  = self.svg.unittouu(doc.get('width'))
		# height = self.svg.unittouu(doc.get('height'))

		#inkex.debug(self.labellinelength)
		#inkex.debug(self.perplineoffset)

		# Put it in the centre of the current view
		centre = self.svg.namedview.center
		cx, cy = centre[0], centre[1]
		# OR use the selected elements to define the center
		if self.useref: # use center of selected element instead of doc.
			# get the bbox centers for each selected node
			bboxes = [node.bounding_box().center for node in self.svg.selected.values()]
			centers = [ (c.x,c.y) for c in bboxes] # turn vectors into lists
			# find average of all centers.
			if len(centers) > 0:
				cx = sum([c[0] for c in centers]) / len(centers)
				cy = sum([c[1] for c in centers]) / len(centers)

		# calc external length from scale
		# mm / min = (km / min)          * ( mm / km )
		#          =                     * ( scale / km / m )
		#          = (speed in kmh / 60) * ( scale * 1000 * 1000 )

		self.mm_per_min = ( convert_speed_to_kph(self.speed, self.speed_unit) / 60 ) * ( 1 / ( self.scale / 1000 / 1000 ))
		self.res = self.mm_per_min / 6

		# Work out how many ticks will fit in the width available
		# Note: could alternatively use paeg width with:
		#       width = self.svg.unittouu(doc.get('width'))
		self.scalefrom = 0
		self.scaleto = int(self.max_length / self.res)
		self.scaleto = self.scaleto - (self.scaleto % 6) + 1
		self.external_length = self.res * (self.scaleto - self.scalefrom)

		# adjust centre for external length
		cx -= self.external_length/2

		centre = (cx,cy)
		grp_transform = 'translate' + str( centre )
		
		# top level group
		grp_name = 'Speed_scale'
		grp_attribs = {inkex.addNS('label','inkscape'):grp_name, 'transform':grp_transform }
		toplevel_group = etree.SubElement(self.svg.get_current_layer(), 'g', grp_attribs)

		# other line, label groups
		grp_name = 'Label_line'
		grp_attribs = {inkex.addNS('label','inkscape'):grp_name}
		label_line = etree.SubElement(toplevel_group, 'g', grp_attribs)

		grp_name = 'Short line'
		grp_attribs = {inkex.addNS('label','inkscape'):grp_name}
		short_line = etree.SubElement(toplevel_group, 'g', grp_attribs)

		grp_name = 'Perpendicular line'
		grp_attribs = {inkex.addNS('label','inkscape'):grp_name}
		perpendicular_line = etree.SubElement(toplevel_group, 'g', grp_attribs)

		grp_name = 'Blank behind labels'
		grp_attribs = {inkex.addNS('label','inkscape'):grp_name}
		self.blank_out_text = etree.SubElement(toplevel_group, 'g', grp_attribs)

		grp_name = 'Labels'
		grp_attribs = {inkex.addNS('label','inkscape'):grp_name}
		labels = etree.SubElement(toplevel_group, 'g', grp_attribs)

		groups = [label_line, short_line, perpendicular_line, self.blank_out_text, labels]	# holds the svg groups for organising the tick marks, labels and perp line

		for i in range(self.scalefrom, self.scaleto):
			self.add_straight_line(i, groups)
		self.add_perpendicular_line(0, perpendicular_line)
		self.add_perpendicular_line(1, perpendicular_line)
		self.add_perpendicular_line(2, perpendicular_line)
		self.add_dimensions(labels)

###
if __name__ == '__main__':
	effect = ScaleGen()
	effect.run()
