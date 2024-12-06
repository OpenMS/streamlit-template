import os
import json
import streamlit as st

def patch_head(document, content):
    return document.replace('<head>', '<head>' + content)

def patch_body(document, content):
    return document.replace('<body>', '<body>' + content)

def google_analytics_head(gtm_tag):
    return f"""
        <script>
        // Define dataLayer and the gtag function.
        window.dataLayer = window.dataLayer || [];
        function gtag(){{dataLayer.push(arguments);}}

        // Set default consent to 'denied' as a placeholder
        // Determine actual values based on your own requirements
        gtag('consent', 'default', {{
            'ad_storage': 'denied',
            'ad_user_data': 'denied',
            'ad_personalization': 'denied',
            'analytics_storage': 'denied'
        }});
        </script>
        <!-- Google Tag Manager -->
        <script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
        new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
        j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
        'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
        }})(window,document,'script','dataLayer','{gtm_tag}');</script>
        <!-- End Google Tag Manager -->
    """

def google_analytics_body(gtm_tag):
    return f"""
        <!-- Google Tag Manager (noscript) -->
        <noscript><iframe src="https://www.googletagmanager.com/ns.html?id={gtm_tag}"
        height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
        <!-- End Google Tag Manager (noscript) -->
    """

def piwik_pro_body(piwik_tag):
    return f"""
    <script type="text/javascript">
    (function(window, document, dataLayerName, id) {{
    window[dataLayerName]=window[dataLayerName]||[],window[dataLayerName].push({{start:(new Date).getTime(),event:"stg.start"}});var scripts=document.getElementsByTagName('script')[0],tags=document.createElement('script');
    function stgCreateCookie(a,b,c){{var d="";if(c){{var e=new Date;e.setTime(e.getTime()+24*c*60*60*1e3),d="; expires="+e.toUTCString();f="; SameSite=Strict"}}document.cookie=a+"="+b+d+f+"; path=/"}}
    var isStgDebug=(window.location.href.match("stg_debug")||document.cookie.match("stg_debug"))&&!window.location.href.match("stg_disable_debug");stgCreateCookie("stg_debug",isStgDebug?1:"",isStgDebug?14:-1);
    var qP=[];dataLayerName!=="dataLayer"&&qP.push("data_layer_name="+dataLayerName),isStgDebug&&qP.push("stg_debug");var qPString=qP.length>0?("?"+qP.join("&")):"";
    tags.async=!0,tags.src="https://openms-web.containers.piwik.pro/"+id+".js"+qPString,scripts.parentNode.insertBefore(tags,scripts);
    !function(a,n,i){{a[n]=a[n]||{{}};for(var c=0;c<i.length;c++)!function(i){{a[n][i]=a[n][i]||{{}},a[n][i].api=a[n][i].api||function(){{var a=[].slice.call(arguments,0);"string"==typeof a[0]&&window[dataLayerName].push({{event:n+"."+i+":"+a[0],parameters:[].slice.call(arguments,1)}})}}}}(i[c])}}(window,"ppms",["tm","cm"]);
    }})(window, document, 'dataLayer', '{piwik_tag}');
    </script>
    """


if __name__ == '__main__':
    
    # Load configuration
    settings_path = os.path.join(os.path.dirname(__file__), '..', 'settings.json')
    with open(settings_path, 'r') as f:
        settings = json.load(f)

    # Load index.html
    index_path = os.path.join(os.path.dirname(st.__file__), 'static', 'index.html')
    with open(index_path, 'r') as f:
        index = f.read()
    
    # Configure google analytics
    if settings['analytics']['google-analytics']['enabled']:
        gtm_tag = settings['analytics']['google-analytics']['tag']
        index = patch_head(index, google_analytics_head(gtm_tag))
        index = patch_body(index, google_analytics_body(gtm_tag))

    # Configure piwik pro
    if settings['analytics']['piwik-pro']['enabled']:
        piwik_tag = settings['analytics']['piwik-pro']['tag']
        index = patch_body(index, piwik_pro_body(piwik_tag))
    
    # Save index.html
    with open(index_path, 'w') as f:
        f.write(index)