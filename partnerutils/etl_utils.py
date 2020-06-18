"""********************************************
* A couple utility functions for working with ArcGIS
********************************************"""
import tempfile
import json
import datetime

DEFAULT_TITLE = 'GeoJSON Utils POC'
DEFAULT_TAG = 'geojson-utils-poc'

def date_to_ags(date):
    """Returns an ArcGIS-formatted date from a Python date object
    
    args:
    date - Python date object"""
    tz = datetime.timezone.utc
    return date.astimezone(tz).strftime('%m/%d/%Y %H:%M:%S')

def timestamp_to_ags(timestamp):
    """Returns an ArcGIS-formatted date from a timestamp
    
    args:
    timestamp -- timestamp in milliseconds since epoch"""
    seconds = timestamp / 1000
    tz = datetime.timezone.utc
    date = datetime.datetime.fromtimestamp(seconds)
    return date_to_ags(date)

def add_geojson(gis, geojson, **item_options):
    """Uploads geojson and returns the file item
    
    args:
    gis -- gis object where item is added
    geojson -- geojson object to upload as file
    item_options -- additional item properties, see here:
    https://developers.arcgis.com/python/api-reference/arcgis.gis.toc.html#arcgis.gis.ContentManager.add"""

    # get default args
    title = item_options.pop('title', DEFAULT_TITLE)
    tags = item_options.pop('tags', DEFAULT_TAG)
        
    # save geojson to tempfile and add as item
    with tempfile.NamedTemporaryFile(mode="w", suffix='.geojson') as fp:
        fp.write(json.dumps(geojson))
        item = gis.content.add({
            **item_options,
            'type': 'GeoJson',
            'title': title,
            'tags': tags,
        }, data=fp.name)
    
    return item

def append_to_layer(gis, layer, geojson, uid_field=None):
    """Appends geojson to an existing service and returns the results

    Note, this is the best approach for bulk updates in ArcGIS Online.
    There are other options here, such as transactional edits
    > https://github.com/mpayson/esri-partner-tools/blob/master/feature_layers/update_data.ipynb
    
    args:
    gis -- gis object where the layers live
    layer -- FeatureLayer to be updated
    geojson -- geojson object to add to the layer
    uid_field -- identifies existing features to update with new features (must be uniquely indexed)
    """

    item = add_geojson(gis, geojson, title="Dataminr update")
    result = None
    try:
        result = layer.append(
            item_id=item.id,
            upload_format="geojson",
            upsert=(uid_field != None),
            upsert_matching_field=uid_field # update existing features with matching uid_fields
        )
    finally:
        item.delete() # if not deleted next run will eror and pollute ArcGIS

    return result

def create_layer(gis, geojson, template_item):
    """Publishes geojson as a hosted service based on an existing template item
    and returns the resulting layer item
    
    args:
    gis -- gis where the layer should live
    geojson -- initial geojson to populate the layer
    template_item -- existing Item that has been pre-configured with desired properties"""

    results = gis.content.clone_items([template_item], copy_data=False)
    item = results[0]
    lyr = item.layers[0]

    append_to_layer(gis, lyr, geojson)

    return item


def create_scratch_layer(gis, geojson, uid_field=None, **item_options):
    """Publishes geojson as a hosted service and returns the layer item

    Note, use this to quickly add geojson with system default properties. In production,
    it's easier to set desired properties on a template layer then use create_layer.
    
    args:
    gis -- gis where the layer should live
    geojson -- initial geojson to populate the layer
    uid_field -- global uid field that can be used to determine existing features on updates
    item_options -- additional item properties, see here:
    https://developers.arcgis.com/python/api-reference/arcgis.gis.toc.html#arcgis.gis.ContentManager.add"""

    item = add_geojson(gis, geojson, **item_options)
    try:
        lyr_item = item.publish()
    finally:
        item.delete()
    
    # add a unique index for upsert operations so don't duplicate rows
    if uid_field:
        new_index = {
          "name": "External UID",
          "fields": uid_field,
          "isUnique": True,
          "description": "External UID for upsert operations"
        } 
        add_dict = {"indexes" : [new_index]}
        lyr = lyr_item.layers[0]
        lyr.manager.add_to_definition(add_dict)
  
    return lyr_item

def get_existing_item(gis, tags=None):
    """Searches for an existing layer item and returns it
    
    Note, for now this just assumes there's just one layer item for the tags
    
    args:
    gis -- gis to search
    tags -- tags to search for layers within the gis"""
    t = tags if tags else DEFAULT_TAG
    search_items = gis.content.search('tags:"{0}" AND type:"Feature Service"'.format(t))
    
    return search_items[0] if len(search_items) > 0 else None